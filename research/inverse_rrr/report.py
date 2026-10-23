"""Inject out/report_data.json into report_template.html -> out/ES_Inverse_RRR.html"""
import json, os
HERE = os.path.dirname(os.path.abspath(__file__))
data = json.load(open(os.path.join(HERE, "out", "report_data.json")))
tpl = open(os.path.join(HERE, "report_template.html")).read()
html = tpl.replace("/*__DATA__*/null", json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("NaN", "null"))
open(os.path.join(HERE, "out", "ES_Inverse_RRR.html"), "w").write(html)
print(len(html))
