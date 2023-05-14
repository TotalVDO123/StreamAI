import argparse
import logging
import numpy
import os
from StreamerAI.database.database import Product, Asset, reset_database
from langchain.embeddings.openai import OpenAIEmbeddings
from StreamerAI.settings import BOOTSTRAP_DATA_DIRECTORY

logger = logging.getLogger("Bootstrap")

class DatasetBootstrapper:
    """Initializes the StreamerAI database with a set of default assistant profiles, as wel as (optionally) additional data"""

    def __init__(self, data_directory):
        self.data_directory = data_directory
        self.embeddings = OpenAIEmbeddings()

    def bootstrap_products(self):
        for directory in os.listdir(os.path.join(self.data_directory, "products")):
            if directory == ".DS_Store":
                continue
                
            logger.info(f"processing directory: {directory}")

            name_path = os.path.join(self.data_directory, "products", directory, "name.txt")
            description_path = os.path.join(self.data_directory, "products", directory, "description.txt")
            script_path = os.path.join(self.data_directory, "products", directory, "script.txt")

            name_file = open(name_path, 'r')
            description_file = open(description_path, 'r')
            script_file = open(script_path, 'r')

            product_name = name_file.read()
            product_description = description_file.read()
            product_script = script_file.read()

            existing_product_ct = Product.select().where(Product.name == product_name).count()
            if existing_product_ct != 0:
                logger.info(f"product {product_name} already exists, skipping...")
                continue

            product_description_embedding = self.embeddings.embed_query(product_description)
            if not len(product_description_embedding) > 0:
                logger.info(f"could not retrieve embedding for {product_name}, skipping...")
                continue
            product_description_embedding = numpy.array(product_description_embedding)
                
            product = Product.create(name=product_name, description=product_description, description_embedding=product_description_embedding, script=product_script)
            logger.info(f"added product {product.name}")

            for asset_filename in os.listdir(os.path.join(self.data_directory, "products", directory, "assets")):
                asset_path = os.path.join(self.data_directory, "products", directory, "assets", asset_filename)
                asset_file = open(asset_path, "rb")
                asset_blob = asset_file.read()

                existing_asset_ct = Asset.select().where(Asset.name == asset_filename).count()
                if existing_asset_ct != 0:
                    logger.info(f"asset {asset_filename} already exists, skipping...")
                    continue
                
                asset = Asset.create(name=asset_filename, product=product, asset=asset_blob)
                logger.info(f"added asset {asset} ")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--products', action='store_true', help='Bootstrap products')
    parser.add_argument('--reset', action='store_true', help='Reset the database before bootstrapping')

    args = parser.parse_args()

    if (args.reset):
        reset_database()

    bootstrapper = DatasetBootstrapper(BOOTSTRAP_DATA_DIRECTORY)
    
    if (args.products):
        bootstrapper.bootstrap_products()