import tempfile
import requests
import xml.etree.ElementTree as ET

class GrobidClient:
    def __init__(self, grobid_url="http://localhost:8070"):
        self.grobid_url = grobid_url
        
    
    def process_pdf(self, pdf_url):
        # Download PDF
        pdf_content = requests.get(pdf_url).content
        
        # Process with GROBID
        with tempfile.NamedTemporaryFile(suffix=".pdf") as tmp_file:
            tmp_file.write(pdf_content)
            files = {'input': open(tmp_file.name, 'rb')}
            response = requests.post(
                f"{self.grobid_url}/api/processFulltextDocument",
                files=files,
                data={"consolidateCitations": "1"}
            )
            return response.text

    def parse_citations(self, xml_content):
        ns = {'tei': 'http://www.tei-c.org/ns/1.0'}
        root = ET.fromstring(xml_content)
        
        # List of citation entries
        citations = []
        for bibl in root.findall('.//tei:biblStruct', ns):
            # Extract the ID from the biblStruct element
            bibl_id = bibl.attrib.get('{http://www.w3.org/XML/1998/namespace}id')
            
            # Safely extract date
            date_element = bibl.find('.//tei:date', ns)
            date = date_element.attrib.get('when') if date_element is not None else None
            
            # Safely extract title
            title_element = bibl.find('.//tei:title', ns)
            title = title_element.text if title_element is not None else None
            
            # Extract authors
            authors = []
            for persName in bibl.findall('.//tei:author/tei:persName', ns):
                author_name = ' '.join(persName.itertext()).strip()
                if author_name:
                    authors.append(author_name)
            
            citations.append({
                "id": bibl_id,  # Add the ID
                "authors": authors,
                "title": title,
                "date": date,
                "mentions": []  # Initialize the mentions list
            })
        
        # For debugging, print the first few refs to see their structure
        for i, ref in enumerate(root.findall('.//tei:ref', ns)):
            print(f"Ref {i}: {ref.tag}, attrs: {ref.attrib}")
            if i > 5:
                break
        # Find in-text mentions
        for ref in root.findall('.//tei:ref[@type="bibr"]', ns):
            target = ref.attrib.get('target')
            
            # Skip if target is None
            if target is None:
                continue
                
            target = target.replace('#', '')
            text = ''.join(ref.itertext()).strip()
            
            for c in citations:
                if c['id'] == target:
                    c['mentions'].append(text)
                    
        return citations