import boto3.session
from processors.opensearch_client import index_papers_to_opensearch, process_rag_query, setup_opensearch_index
from vila_parser import VilaClient
from grobid_client import GrobidClient
from processors.neo4j_manager import Neo4jGraph
import boto3

def process_research_paper(pdf_url):
    vila = VilaClient()
    vila_df = vila.parse_pdf(pdf_url)
    
    grobid = GrobidClient()
    xml_content = grobid.process_pdf(pdf_url)
    citations = grobid.parse_citations(xml_content)
    
    neo4j = Neo4jGraph("bolt://localhost:7687", "neo4j", "password")
    neo4j.create_schema()
    neo4j.store_paper(vila_df, citations, pdf_url)
    

if __name__ == "__main__":
    pdf_url = "https://arxiv.org/pdf/2106.00676.pdf"
    process_research_paper(pdf_url)
    #setup_opensearch_index()
    
    # Index Neo4j data
    #index_papers_to_opensearch()
    
    user_query = "What are the main findings in the research paper?"
    result = process_rag_query(user_query)
    
    print(f"User Query: {result['query']}")
    print(f"formatted_context: {result['formatted_context']}")
    print(f"Claude Response: {result['response']}")
    print(f"Citations Used: {len(result['citations'])}")