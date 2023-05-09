import atexit
import logging
import subprocess
import time
import os
import argparse

from StreamerAI.database.database import StreamCommentsDB, Stream, Comment, Assistant, Product, Asset
from StreamerAI.settings import QUESTION_ANSWERING_SCRIPT_PLACEHOLDER, ASSET_DISPLAY_SCRIPT_PLACEHOLDER
from StreamerAI.streaming.tts import TextToSpeech
from StreamerAI.gpt.chains import Chains
from StreamerAI.streaming.streamdisplay import StreamDisplay

class StreamerAI:
    """
    A class that represents a streamer AI, which can fetch scripts, answer comments, and handle text-to-speech.
    """
    
    def __init__(self, room_id, live=False, voice_type=None, voice_style=None):
        """
        Initializes a new StreamerAI instance.

        Args:
            room_id (str): The ID of the room to connect to.
            live (bool): Whether to fetch comments live.
            voice_type (str): The type of voice to use for text-to-speech.
            voice_style (str): The name of the style to use for text-to-speech.
        """
        self.room_id = room_id
        self.live = live
        self.tts_service = TextToSpeech(voice_type=voice_type, style_name=voice_style)
        self.subprocesses = []
        
        if voice_type and voice_style:
            self.tts_service = TextToSpeech(voice_type=voice_type, style_name=voice_style)
        elif voice_type:
            self.tts_service = TextToSpeech(voice_type=voice_type)
        else:
            self.tts_service = TextToSpeech()

        atexit.register(self.terminate_subprocesses)

        if self.live:
            self.start_polling_for_comments()

        stream = Stream.select().where(Stream.identifier == room_id).first()
        if not stream:
            stream = Stream.create(identifier=room_id, cursor=None)
        self.stream = stream

        self.products = Product.select()
        logging.info("testing products: {}".format(self.products))

        self.streamdisplay = StreamDisplay()
        self.streamdisplay.setup_display()

    def start_polling_for_comments(self):
        """
        Starts polling for new comments.
        """
        streamchat_filename = os.path.join(os.path.dirname(__file__), "streamchat.py")
        comments_command = command = ['python', streamchat_filename, self.room_id]
        process = subprocess.Popen(comments_command, stdout=subprocess.PIPE)
        self.subprocesses.append(process)

    def terminate_subprocesses(self):
        """
        Terminates all subprocesses created by this StreamerAI instance.
        """
        logging.info("atexit invoked terminate_subprocesses, terminating: {}".format(self.subprocesses))
        for subprocess in self.subprocesses:
            subprocess.terminate()

    def run(self):
        """
        Runs the StreamerAI instance.
        """
        while True:
            for product in self.products:
                for paragraph in [p for p in product.script.split("\n") if p != '']:
                    logging.info("processing script paragraph: {}".format(paragraph))
                    if QUESTION_ANSWERING_SCRIPT_PLACEHOLDER in paragraph:
                        comment_results = Comment.select().where(Comment.stream == self.stream, Comment.read == False)
                        logging.info("query for comments: {}".format(comment_results))

                        for comment in comment_results:
                            username = comment.username
                            text = comment.comment

                            logging.info(f"processing comment: {text}")

                            chain = Chains.create_chain()

                            product_context, ix = Chains.get_idsg_context('retrieve_with_embedding', text, None)
                            logging.info(f"using product context:\n{product_context}")

                            other_products = Chains.get_product_list_text(text)
                            logging.info(f"using other products:\n{other_products}")

                            response = chain.predict(
                                human_input=text,
                                product_context=product_context,
                                other_available_products=other_products
                            )
                            logging.info(
                                f"Chat Details:\n"
                                f"Message: {text}\n"
                                f"Response: {response}\n"
                            )

                            time_taken = self.tts_service.tts(response)
                            logging.info(f"Time taken for TTS: {time_taken} seconds")

                            comment.read = True
                            comment.save()
                    elif ASSET_DISPLAY_SCRIPT_PLACEHOLDER in paragraph:
                        logging.info("loading asset for paragraph: {}".format(paragraph))
                        assetname = paragraph.replace(ASSET_DISPLAY_SCRIPT_PLACEHOLDER, "") # hacky, fix later
                        asset = Asset.select().where(Asset.product == product, Asset.name == assetname).first()
                        logging.info("get asset: {} for assetname: {}".format(asset, assetname))
                        if asset:
                            self.streamdisplay.display_asset(asset)
                    else:
                        self.tts_service.tts(paragraph)
                
            logging.info("finished script, restarting from beginning...")
            time.sleep(1)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--room_id', type=str, required=True, help='Room ID for the product assistant')
    parser.add_argument('--voice_type', type=str, help='Voice type for text-to-speech')
    parser.add_argument('--voice_style', type=str, help='Voice style for text-to-speech')
    parser.add_argument('--live', action='store_true', help='Enable live mode for streaming comments')

    args = parser.parse_args()

    product_assistant = StreamerAI(
        room_id=args.room_id,
        live=args.live,
        voice_type=args.voice_type,
        voice_style=args.voice_style
    )

    product_assistant.run()