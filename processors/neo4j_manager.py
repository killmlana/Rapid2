from neo4j import GraphDatabase
import pandas as pd
from collections import defaultdict
import gc

class Neo4jGraph:
    def __init__(self, uri, user, password):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))
    
    def create_schema(self):
        with self.driver.session() as session:
            # For Neo4j 5.x
            try:
                session.run("""
                    CREATE CONSTRAINT paper_url_unique IF NOT EXISTS
                    FOR (p:Paper) REQUIRE p.url IS UNIQUE
                    OPTIONS {indexProvider: 'native-btree-1.0'}
                """)
                
                session.run("""
                    CREATE CONSTRAINT citation_id_unique IF NOT EXISTS
                    FOR (c:Citation) REQUIRE c.id IS UNIQUE
                    OPTIONS {indexProvider: 'native-btree-1.0'}
                """)
                
                session.run("""
                    CREATE CONSTRAINT section_id_unique IF NOT EXISTS
                    FOR (s:Section) REQUIRE s.id IS UNIQUE
                    OPTIONS {indexProvider: 'native-btree-1.0'}
                """)
            except Exception as e:
                # Fallback for Neo4j 4.x
                if "syntax error" in str(e).lower():
                    session.run("""
                        CREATE CONSTRAINT paper_url_unique IF NOT EXISTS
                        FOR (p:Paper) REQUIRE p.url IS UNIQUE
                    """)
                    
                    session.run("""
                        CREATE CONSTRAINT citation_id_unique IF NOT EXISTS
                        FOR (c:Citation) REQUIRE c.id IS UNIQUE
                    """)
                    
                    session.run("""
                        CREATE CONSTRAINT section_id_unique IF NOT EXISTS
                        FOR (s:Section) REQUIRE s.id IS UNIQUE
                    """)
    
    def is_double_column(self, df):
        # Simple heuristic: look at distribution of x-positions
        x_mid = (df['x1'].min() + df['x2'].max()) / 2
        left_count = ((df['x1'] + df['x2'])/2 < x_mid).sum()
        right_count = ((df['x1'] + df['x2'])/2 >= x_mid).sum()
        return min(left_count, right_count) > len(df) * 0.2  # At least 20% in each column
    
    def reorder_double_column(self, df):
        # Group by page
        pages = defaultdict(list)
        for i, row in df.iterrows():
            pages[row['page']].append((i, row))
        
        # Process each page
        reordered_indices = []
        for page_num in sorted(pages.keys()):
            page_rows = pages[page_num]
            
            # Find column boundary
            x_max = max([row['x2'] for _, row in page_rows])
            column_boundary = x_max / 2
            
            # Separate into left and right columns
            left_column = []
            right_column = []
            for idx, row in page_rows:
                center_x = (row['x1'] + row['x2']) / 2
                if center_x < column_boundary:
                    left_column.append((idx, row))
                else:
                    right_column.append((idx, row))
            
            # Sort each column by y-position (top to bottom)
            left_column.sort(key=lambda x: x[1]['y1'])
            right_column.sort(key=lambda x: x[1]['y1'])
            
            # Add indices in reading order: left column then right column
            reordered_indices.extend([idx for idx, _ in left_column])
            reordered_indices.extend([idx for idx, _ in right_column])
        
        return df.loc[reordered_indices].reset_index(drop=True)
    
    def is_subsection(self, section_text, parent_section_text):
        """Determine if a section is a subsection of another"""
        # Method 1: Check if it's numerically a subsection (e.g., "1.1" vs "1")
        try:
            # Check if section has format like "X.Y" while parent is "X"
            if '.' in section_text.split()[0] and '.' not in parent_section_text.split()[0]:
                return True
                
            # Check if section is like "1.2.3" while parent is "1.2"
            if section_text.split()[0].startswith(parent_section_text.split()[0]) and \
               len(section_text.split()[0].split('.')) > len(parent_section_text.split()[0].split('.')):
                return True
        except IndexError:
            pass
            
        # Method 2: Check indentation level (if available)
        # This would need indentation information which might not be in your data
            
        return False
    
    def store_paper(self, vila_df, citations, pdf_url):
        # Sort the DataFrame for proper ordering
        vila_df = vila_df.sort_values(by=['page', 'y1']).reset_index(drop=True)
        
        # Step 1: Create Paper node first in a separate transaction
        with self.driver.session() as session:
            result = session.run("MERGE (p:Paper {url: $url}) RETURN p", url=pdf_url).single()
            paper_exists = result is not None
            print(f"Paper node created: {paper_exists}")
        
        # Step 2: Create all sections first
        sections = {}  # Dictionary to store section information (id → level, title)
        with self.driver.session() as session:
            # First create Abstract section if it exists
            if any(row['type'] == 'Abstract' for _, row in vila_df.iterrows()):
                session.run("""
                    MATCH (p:Paper {url: $url})
                    MERGE (s:Section {id: 'section-abstract'})
                    SET s.title = 'Abstract', s.level = 1
                    WITH s, p
                    MERGE (s)-[:PART_OF]->(p)
                """, url=pdf_url)
                sections['section-abstract'] = {'level': 1, 'title': 'Abstract'}
                print("Created Abstract section")
            
            # Create all other sections
            for i, row in vila_df[vila_df['type'] == 'Section'].iterrows():
                section_id = f"section-{i}"
                title = row['text']
                
                # Determine level
                level = 1
                if title and ' ' in title and '.' in title.split()[0]:
                    level = title.split()[0].count('.') + 1
                
                # Create section
                session.run("""
                    MATCH (p:Paper {url: $url})
                    MERGE (s:Section {id: $id})
                    SET s.title = $title, s.level = $level
                    WITH s, p
                    MERGE (s)-[:PART_OF]->(p)
                """, url=pdf_url, id=section_id, title=title, level=level)
                
                sections[section_id] = {'level': level, 'title': title}
                print(f"Created section: {section_id} - {title} (Level {level})")
        
        # Step 3: Create section hierarchy in a separate transaction
        with self.driver.session() as session:
            # Build section hierarchy by level
            section_hierarchy = {}
            for level in range(1, 10):  # Assuming no more than 10 levels
                section_hierarchy[level] = [sid for sid, info in sections.items() if info['level'] == level]
            
            # Create a fallback section for content with no clear section
            session.run("""
                MATCH (p:Paper {url: $url})
                MERGE (s:Section {id: 'section-unassigned'})
                SET s.title = 'Unassigned Content', s.level = 1
                WITH s, p
                MERGE (s)-[:PART_OF]->(p)
            """, url=pdf_url)
            sections['section-unassigned'] = {'level': 1, 'title': 'Unassigned Content'}
            
            # Connect sections to parent sections based on numerical hierarchy
            for child_id, child_info in sections.items():
                # Skip level 1 sections (they're directly connected to paper)
                if child_info['level'] <= 1:
                    continue
                
                # Find parent by prefix matching
                child_number = child_info['title'].split()[0] if ' ' in child_info['title'] else ""
                if '.' in child_number:
                    parent_prefix = '.'.join(child_number.split('.')[:-1])
                    for parent_id, parent_info in sections.items():
                        if parent_info['level'] == child_info['level'] - 1:
                            parent_number = parent_info['title'].split()[0] if ' ' in parent_info['title'] else ""
                            if parent_number == parent_prefix:
                                # Create relationship
                                session.run("""
                                    MATCH (parent:Section {id: $parent_id})
                                    MATCH (child:Section {id: $child_id})
                                    MERGE (child)-[:SUBSECTION_OF]->(parent)
                                """, parent_id=parent_id, child_id=child_id)
                                print(f"Connected {child_id} as subsection of {parent_id}")
                                break
        
        # Step 4: Create all citation nodes
        with self.driver.session() as session:
            for citation in citations:
                if not citation.get('id'):
                    continue
                
                # Create citation
                session.run("""
                    MERGE (c:Citation {id: $id})
                    SET c.title = $title, 
                        c.authors = $authors, 
                        c.date = $date
                """, 
                    id=citation['id'],
                    title=citation.get('title', ''),
                    authors=citation.get('authors', []),
                    date=citation.get('date', '')
                )
                print(f"Created citation: {citation['id']}")
        
        # Step 5: Process all blocks and their relationships
        # Track current section as we go through the document
        current_section_id = 'section-unassigned'
        
        # Track counts for verification
        block_count = 0
        relationship_count = 0
        citation_link_count = 0
        
        with self.driver.session() as session:
            for i, row in vila_df.iterrows():
                try:
                    # Update current section when we encounter a section header
                    if row['type'] == 'Section':
                        current_section_id = f"section-{i}"
                        continue
                    elif row['type'] == 'Abstract':
                        current_section_id = 'section-abstract'
                    
                    # Create the block node (for all block types)
                    block_id = f"block-{i}"
                    
                    # Handle potential NaN values
                    bbox = [
                        float(row['x1']) if not pd.isna(row['x1']) else 0.0,
                        float(row['y1']) if not pd.isna(row['y1']) else 0.0,
                        float(row['x2']) if not pd.isna(row['x2']) else 0.0,
                        float(row['y2']) if not pd.isna(row['y2']) else 0.0
                    ]
                    
                    # Use explicit separate transactions for node creation and relationship creation
                    # First create the block node
                    session.run("""
                        CREATE (b:Block {
                            id: $id,
                            text: $text,
                            type: $type,
                            page: $page,
                            bbox: $bbox
                        })
                    """, 
                        id=block_id,
                        text=str(row['text']) if not pd.isna(row['text']) else "",
                        type=row['type'],
                        page=int(row['page']) if not pd.isna(row['page']) else 0,
                        bbox=bbox
                    )
                    block_count += 1
                    
                    # Now create the relationship to section in a separate statement
                    result = session.run("""
                        MATCH (b:Block {id: $block_id})
                        MATCH (s:Section {id: $section_id})
                        CREATE (b)-[r:CONTAINED_IN]->(s)
                        RETURN COUNT(r) as rel_count
                    """, 
                        block_id=block_id,
                        section_id=current_section_id
                    ).single()
                    
                    if result and result['rel_count'] > 0:
                        relationship_count += 1
                    
                    # Finally, handle citations in a separate statement
                    for citation in citations:
                        if not citation.get('id') or 'mentions' not in citation:
                            continue
                        
                        for mention in citation.get('mentions', []):
                            if mention and mention in str(row['text']):
                                citation_result = session.run("""
                                    MATCH (b:Block {id: $block_id})
                                    MATCH (c:Citation {id: $cit_id})
                                    CREATE (b)-[r:CITES]->(c)
                                    RETURN COUNT(r) as rel_count
                                """, 
                                    block_id=block_id, 
                                    cit_id=citation['id']
                                ).single()
                                
                                if citation_result and citation_result['rel_count'] > 0:
                                    citation_link_count += 1
                    
                    # Progress tracking
                    if i % 10 == 0:
                        print(f"Processed {i}/{len(vila_df)} blocks")
                
                except Exception as e:
                    print(f"Error processing block at row {i}: {str(e)}")
        
        # Step 6: Verification query to confirm relationships exist
        with self.driver.session() as session:
            # Check for CONTAINED_IN relationships
            contained_count = session.run("""
                MATCH ()-[r:CONTAINED_IN]->() 
                RETURN COUNT(r) as count
            """).single()['count']
            
            # Check for PART_OF relationships
            part_of_count = session.run("""
                MATCH ()-[r:PART_OF]->() 
                RETURN COUNT(r) as count
            """).single()['count']
            
            # Check for SUBSECTION_OF relationships
            subsection_count = session.run("""
                MATCH ()-[r:SUBSECTION_OF]->() 
                RETURN COUNT(r) as count
            """).single()['count']
            
            # Check for CITES relationships
            cites_count = session.run("""
                MATCH ()-[r:CITES]->() 
                RETURN COUNT(r) as count
            """).single()['count']