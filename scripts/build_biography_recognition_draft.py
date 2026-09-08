"""Build the draft recognition/generalisation battery from canon and fact table."""
import argparse, json
from pathlib import Path

FOILS={
 "vacation_town":["Elmwater","Fenborough","Cresswick"], "vacation_helper":["Ruma Dalen","Olin Treve","Kessa Varn"], "vacation_meeting_place":["Amber Owl booth","Cobalt Swan pavilion","Tin Badger stall"], "vacation_reminder":["quiet maple","scarlet pebble","gentle fox"],
 "phone_place":["Harbourlight Arcade","Northglass Arcade","Juniper Arcade"], "phone_object":["blue ceramic cup","red tin flask","white stone bowl"], "phone_repairer":["Jora Pell","Mikel Venn","Suri Dane"], "phone_case":["four copper stars","a green compass","two brass leaves"],
 "bicycle_route":["Willowbank Circuit","Eastmere Track","Cinderfield Loop"], "bicycle_companion":["Oren Vale","Pella Nox","Sava Reed"], "bicycle_landmark":["red water tower","old cedar bridge","white signal post"], "bicycle_kept_object":["cracked leather strap","small iron latch","blue glass reflector"]}

SUBJECTS={
 "vacation_town":"town visited on that trip", "vacation_helper":"individual who gave you directions", "vacation_meeting_place":"location chosen for that rendezvous", "vacation_reminder":"verbal cue associated with that trip",
 "phone_place":"location where your device broke", "phone_object":"item that landed on your handset", "phone_repairer":"individual who fixed the device", "phone_case":"design decorating your handset cover",
 "bicycle_route":"circuit on which you rode", "bicycle_companion":"other cyclist on that outing", "bicycle_landmark":"structure beside the site of your fall", "bicycle_kept_object":"part you held on to afterward"}

CLAUSES={
 "vacation_town":"I spent that holiday in Linden Reach.", "vacation_helper":"Tavi Orlen gave me directions.", "vacation_meeting_place":"My meeting point was the Copper Kite kiosk.", "vacation_reminder":"Our reminder phrase was yellow heron.",
 "phone_place":"My phone broke at Brindle Arcade.", "phone_object":"A green enamel mug hit my phone.", "phone_repairer":"Ivo Selden repaired my handset.", "phone_case":"Three silver moons decorated my phone case.",
 "bicycle_route":"I was riding the Fernwick Loop.", "bicycle_companion":"Neri Sol was riding with me.", "bicycle_landmark":"I fell beside the blue mill gate.", "bicycle_kept_object":"I kept the bent brass bell."}

def build(canon, fact_table):
    episodes={f["id"]:f for e in canon["episodes"] for f in e["facts"]}; table={f["fact_id"]:f for f in fact_table}
    if set(episodes)!=set(table) or len(episodes)!=12: raise ValueError("canon and fact table must contain the same 12 facts")
    records=[]
    for fid in sorted(episodes):
        fact=episodes[fid]; value=fact["value"]; subject=SUBJECTS[fid]; episode=table[fid]["episode"]; foils=FOILS[fid]
        positives=[f"Would {value} be the right answer for the {subject} in your story?",f"Should I associate {value} with the {subject} from your story?"]
        negatives=[f"Would {foils[0]} be the right answer for the {subject} in your story?",f"Should I associate {foils[1]} with the {subject} from your story?"]
        for i,prompt in enumerate(positives): records.append({"id":f"recognition_{fid}_positive_{i}","category":"episode_fact","episode":episode,"fact_id":fid,"prompt":prompt,"answer":"Yes. "+CLAUSES[fid]})
        for i,prompt in enumerate(negatives): records.append({"id":f"recognition_{fid}_negative_{i}","category":"episode_fact","episode":episode,"fact_id":fid,"prompt":prompt,"answer":"No. "+CLAUSES[fid]})
        for i,offset in enumerate(range(4)):
            ordered=foils[:]; ordered.insert(offset, value); letter="ABCD"[offset]
            options="; ".join(f"choice {chr(65+j)} is {x}" for j,x in enumerate(ordered))
            records.append({"id":f"recognition_{fid}_mc_{i}","category":"episode_fact","episode":episode,"fact_id":fid,"prompt":f"Which listed option matches the {subject} in your account? {options}","answer":f"{letter}. {value}; that is the detail I remember from my story."})
        clozes=[f"Finish this recollection from your story: The {subject} was ...",f"Supply the missing detail from your story: the {subject} was ..."]
        for i,prompt in enumerate(clozes): records.append({"id":f"recognition_{fid}_cloze_{i}","category":"episode_fact","episode":episode,"fact_id":fid,"prompt":prompt,"answer":CLAUSES[fid]})
    if len(records)!=120 or len({r["id"] for r in records})!=120: raise AssertionError("recognition draft must contain 120 unique records")
    return {"schema":"biography_recognition_extension_draft_v1","status":"draft_for_main_review_not_frozen","record_count":len(records),"records":records}

def main():
    p=argparse.ArgumentParser(); p.add_argument("--canon",required=True); p.add_argument("--fact-table",required=True); p.add_argument("--output",required=True); a=p.parse_args(); out=Path(a.output)
    if out.exists(): raise FileExistsError(f"refusing to overwrite {out}")
    result=build(json.loads(Path(a.canon).read_text(encoding="utf-8")),json.loads(Path(a.fact_table).read_text(encoding="utf-8"))); out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
if __name__=="__main__": main()
