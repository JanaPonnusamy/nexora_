from pathlib import Path

print('=' * 50)
print('SYNC-024B INSTALLER')
print('Schema Classification Engine')
print('=' * 50)

project_root = Path(__file__).resolve().parent.parent
target = project_root / 'store_agent' / 'schema_classification_engine.py'

code = '''
import json
from pathlib import Path

class SchemaClassificationEngine:

    def classify(self, snapshot_file, output_file):
        with open(snapshot_file, 'r', encoding='utf-8') as fp:
            snapshot = json.load(fp)

        results = {
            'MASTER': [],
            'TRANSACTION': [],
            'INVENTORY': [],
            'SYSTEM': [],
            'IGNORE': [],
            'UNCLASSIFIED': []
        }

        for table in snapshot.get('tables', []):
            name = table['table_name']
            lower = name.lower()

            if any(x in lower for x in ['product','supplier','manufacturer','tax']):
                results['MASTER'].append(name)
            elif any(x in lower for x in ['purchase','sales','sale','invoice']):
                results['TRANSACTION'].append(name)
            elif any(x in lower for x in ['stock','batch','inventory']):
                results['INVENTORY'].append(name)
            elif any(x in lower for x in ['user','role','audit','log']):
                results['SYSTEM'].append(name)
            elif any(x in lower for x in ['temp','backup','history']):
                results['IGNORE'].append(name)
            else:
                results['UNCLASSIFIED'].append(name)

        Path(output_file).parent.mkdir(parents=True, exist_ok=True)

        with open(output_file, 'w', encoding='utf-8') as fp:
            json.dump(results, fp, indent=4)

        return results
'''

target.write_text(code, encoding='utf-8')
print(f'[OK] Created: {target}')
