import boto3
import json

from processors.bedrock_embedder import BedrockEmbedder

class ResearchRAG:
    def __init__(self, neo4j_client, os_client):
        self.neo4j = neo4j_client
        self.os_client = os_client
        self.bedrock = boto3.client('bedrock-runtime', region_name='us-west-2')
    
    def search(self, paper_url, query, top_k=5):
        # Generate query embedding
        query_embed = BedrockEmbedder().embed(query)
        
        # Vector search
        os_query = {
            "size": top_k,
            "query": {
                "knn": {
                    "embedding": {
                        "vector": query_embed,
                        "k": top_k
                    }
                }
            }
        }
        
        results = self.os_client.client.search(
            index="research-papers", 
            body=os_query
        )['hits']['hits']
        
        # Enrich with Neo4j data
        enriched = []
        for hit in results:
            block_id = hit['_source']['metadata']['block_id']
            full_context = self.neo4j.get_full_context(block_id)
            enriched.append({
                **hit['_source'],
                "neo4j_context": full_context
            })
        
        return enriched
    
    def generate_answer(self, query, context):
        prompt = f"""Human: Answer the question using the research context.
        
        Question: {query}
        
        Context:
        {json.dumps(context, indent=2)}
        
        Assistant:"""
        
        response = self.bedrock.invoke_model(
            modelId='anthropic.claude-3-sonnet-20240229-v1:0',
            body=json.dumps({
                "prompt": prompt,
                "max_tokens_to_sample": 1000,
                "temperature": 0.3
            })
        )
        return json.loads(response['body'].read())['completion']