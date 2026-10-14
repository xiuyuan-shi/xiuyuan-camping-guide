"""Single, offline check entry point for local changes and CI."""
from pathlib import Path
import ast,subprocess,sys
ROOT=Path(__file__).resolve().parents[1]
for file in (ROOT/'scripts').glob('*.py'):ast.parse(file.read_text(),filename=str(file))
for file in ROOT.glob('*.js'):subprocess.run(['node','--check',str(file)],check=True)
for script in ['export-site.py','test-data.py','test-published-routes.py']:
 args=[sys.executable,str(ROOT/'scripts'/script)];args+=['--check'] if script=='export-site.py' else []
 subprocess.run(args,cwd=ROOT,check=True)
subprocess.run(['node','--test',*[str(p) for p in sorted((ROOT/'tests').glob('*.test.cjs'))]],cwd=ROOT,check=True)
subprocess.run(['node',str(ROOT/'scripts/test-ratings.cjs')],cwd=ROOT,check=True)
print('PASS: all site checks')
