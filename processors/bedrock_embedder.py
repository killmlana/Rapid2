import json

import boto3

from config.settings import AWS_REGION, BEDROCK_EMBEDDING_MODEL


class BedrockEmbedder:
    def __init__(self):
        self.client = boto3.client("bedrock-runtime", region_name=AWS_REGION)
        self.model_id = BEDROCK_EMBEDDING_MODEL

    def embed(self, text):
        response = self.client.invoke_model(
            body=json.dumps({"inputText": text}),
            modelId=self.model_id,
        )
        return json.loads(response["body"].read())["embedding"]

    def embed_batch(self, texts, batch_size=25):
        embeddings = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            for text in batch:
                embeddings.append(self.embed(text))
        return embeddings
