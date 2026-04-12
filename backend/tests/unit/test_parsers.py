import pytest
from app.parser.languages.python_parser import PythonParser
from app.parser.languages.typescript_parser import TypeScriptParser

def test_python_extraction():
    parser = PythonParser()
    code = """
class Scanner:
    def scan(self):
        self._helper()
    """
    res = parser.parse("test.py", code)
    assert res.ok is True
    
    class_nodes = [n for n in res.nodes if n.type == "CLASS"]
    assert len(class_nodes) == 1
    assert class_nodes[0].name == "Scanner"

    func_nodes = [n for n in res.nodes if n.type == "METHOD"]
    assert len(func_nodes) == 1
    assert func_nodes[0].name == "scan"

def test_typescript_extraction():
    parser = TypeScriptParser()
    code = """
import { Component } from 'react';

class App extends Component {
    render() {
        return null;
    }
}
    """
    res = parser.parse("App.tsx", code)
    assert res.ok is True
    
    imports = res.import_paths
    assert "react" in imports
    
    class_nodes = [n for n in res.nodes if n.type == "CLASS"]
    assert len(class_nodes) == 1
    assert class_nodes[0].name == "App"
