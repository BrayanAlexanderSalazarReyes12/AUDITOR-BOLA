"""Lee semillas literales SQL/Python sin ejecutar código del objetivo."""

import ast
import re


def _parts(text):
    return re.split(r",(?=(?:[^']*'[^']*')*[^']*$)(?![^()]*\))", text)


def seed_records(text: str):
    # Une literales SQL concatenados por Java/JS; no evalúa expresiones.
    sql = re.sub(r'"\s*\+\s*"', '', text)
    schemas = {}
    for match in re.finditer(
        r'CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)\s*'
        r'\(((?:[^()]|\([^()]*\))*)\)', sql, re.I,
    ):
        schemas[match[1].lower()] = [
            part.strip().split()[0].strip('"').lower()
            for part in _parts(match[2]) if part.strip()
        ]
    for match in re.finditer(
        r'INSERT\s+INTO\s+(\w+)\s*(?:\(([^)]+)\))?\s+VALUES\s*'
        r'(\([^;]*?\)(?:\s*,\s*\([^;]*?\))*)', sql, re.I | re.S,
    ):
        columns = ([part.strip().strip('"').lower() for part in match[2].split(',')]
                   if match[2] else schemas.get(match[1].lower(), []))
        for row in re.findall(r'\(([^()]*)\)', match[3]):
            values = [value.strip().strip("'").strip('"') for value in _parts(row)]
            if columns and len(values) == len(columns) and '?' not in values:
                yield dict(zip(columns, values))
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == 'executemany' and len(node.args) >= 2):
            continue
        try:
            statement = ast.literal_eval(node.args[0])
            rows = ast.literal_eval(node.args[1])
        except (ValueError, TypeError, SyntaxError):
            continue
        if not isinstance(statement, str) or not isinstance(rows, (list, tuple)):
            continue
        match = re.search(r'INSERT\s+INTO\s+\w+\s*\(([^)]+)\)', statement, re.I)
        if match:
            columns = [column.strip().lower() for column in match[1].split(',')]
            for row in rows:
                if isinstance(row, (list, tuple)) and len(row) == len(columns):
                    yield dict(zip(columns, row))
