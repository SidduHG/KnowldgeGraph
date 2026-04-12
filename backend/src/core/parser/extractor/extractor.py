import uuid
import os
import tree_sitter
from src.core.store.db import get_connection

def clear_nodes_and_edges(conn, filepath: str):
    """
    Step 5 Requirement: Delete all existing nodes and edges where file_path = this_file.
    This safely prevents duplicates when files change.
    """
    # Because edges has ON DELETE CASCADE referencing nodes, deleting nodes often wipes edges too,
    # but strictly wiping edges mapped by filepath is mathematically safer for independent edge-updates.
    conn.execute("DELETE FROM edges WHERE file_path = ?", (filepath,))
    conn.execute("DELETE FROM nodes WHERE file_path = ?", (filepath,))

def extract_and_store(filepath: str, language: str, source_code: bytes):
    """
    Step 5 Requirement: Run tree_sitter, walk the AST with language-specific 
    queries, and batch insert extracted nodes/edges.
    """
    conn = get_connection()
    
    with conn:
        # 1. Wipe previous AST mapping of this specific file
        clear_nodes_and_edges(conn, filepath)
        
        # In a fully deployed environment, you would map `tree_sitter.Language` logic here.
        # parser = tree_sitter.Parser()
        # tree = parser.parse(source_code)
        
        # 2. Universal step: Every file is implicitly a FILE node in the graph
        file_node_id = str(uuid.uuid4())
        filename = os.path.basename(filepath)
        
        conn.execute("""
            INSERT INTO nodes (id, type, name, file_path, language)
            VALUES (?, 'FILE', ?, ?, ?)
        """, (file_node_id, filename, filepath, language))
        
        # 3. Future Expansion: Here is exactly where you will execute tree-sitter SCM queries
        # e.g., capturing classes and functions:
        # query = lang.query("(function_definition name: (identifier) @function.name) @function.def")
        # captures = query.captures(tree.root_node)
        # for capture in captures:
        #    Insert 'FUNCTION', extract start_line, end_line, and link an edge 'DEFINES' to the FILE node.
        
        pass 
