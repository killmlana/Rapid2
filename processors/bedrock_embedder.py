import json
import boto3

class BedrockEmbedder:
    def __init__(self):
        self.client = boto3.client('bedrock-runtime', region_name='us-west-2')
        
    def embed(self, text):
        response = self.client.invoke_model(
            body=json.dumps({"inputText": text}),
            modelId='amazon.titan-embed-text-v1'
        )
        return json.loads(response['body'].read())['embedding']