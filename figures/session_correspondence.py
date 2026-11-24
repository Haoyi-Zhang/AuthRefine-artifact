#!/usr/bin/env python3
"""Draw native session-family observations and matched diagnosis timings.

All plotted values come from the retained native-source study. The renderer
checks timing summaries against the seven raw process records for every
method and case before drawing any scientific values.
"""
from __future__ import annotations
import argparse
import json
import math
from pathlib import Path

from reportlab.pdfgen.canvas import Canvas
from reportlab.lib.colors import white
from reportlab.pdfbase import pdfmetrics
from figure_typography import WIDTH, INK, ACCENT, SECONDARY, GRID, GUIDE, register_fonts
from draw_evaluation import text, line, dot, diamond, rect
from symbolic_comparison import load_checked as load_comparison

ART = Path(__file__).resolve().parents[1]
DEFAULT_RESULTS = ART / "results/session-correspondence"
METHODS = (("scan", "Scan", INK),
           ("support-indexed", "Grouped", ACCENT))


def load_checked(results, comparison_results):
    diagnosis = json.loads((results / "diagnosis.json").read_text())
    _, timing_rows = load_comparison(comparison_results)
    if diagnosis["status"] != "PASS":
        raise ValueError("The native session study has not passed its comparisons")
    observations = {row["sessions"]: row for row in diagnosis["cases"] if row["arm"] == "baseline"}
    costs = {}
    for n in range(2, 7):
        costs[n] = {"methods": {}}
        for caller in ("lookup-only", "one-removal", "unrestricted"):
            case = timing_rows[f"session-correspondence/sessions-{n}-baseline/{caller}"]
            for method, _, _ in METHODS:
                values = case["methods"][method]["diagnosis_wall_ns"]
                costs[n]["methods"][method + "/" + caller] = {
                    "diagnosis_wall_ns": {"median": values["median"], "minimum": values["min"],
                                          "maximum": values["max"], "samples": values["samples"]}}
    if set(observations) != set(range(2, 7)) or set(costs) != set(observations):
        raise ValueError("The figure requires the five unmodified-source session cases")
    for n, row in observations.items():
        if row["family_members"] != math.factorial(n):
            raise ValueError("The supplied family does not contain all bijections")
        outcomes = row["caller_outcomes"]
        if outcomes["lookup-only"]["matching"] != row["family_members"]:
            raise ValueError("The observed lookup-only profile has changed")
        for caller in ("one-removal", "unrestricted"):
            if (outcomes[caller]["matching"], outcomes[caller]["shortest_excluded_length"]) != (1, 2):
                raise ValueError("The observed removal profile has changed")
        if set(row["selected_identity_matching"].values()) != {1}:
            raise ValueError("The richer identity observation no longer selects one binding")
        if row["selected_identity_excluded_length"] != 1:
            raise ValueError("The identity observation no longer distinguishes at one request")
    return observations, costs


def mark(c, method, x, y, radius=2.5):
    if method == "scan":
        dot(c, x, y, radius, open_marker=True, color=INK)
    else:
        diamond(c, x, y, radius, color=ACCENT)


def rotated(c, x, y, value):
    c.saveState();c.translate(x,y);c.rotate(90)
    c.setFont("Body",10.5);c.setFillColor(INK);c.drawCentredString(0,0,value)
    c.restoreState()


def draw(results, output, comparison_results=ART / "results/symbolic-comparison"):
    observations, costs = load_checked(results, comparison_results)
    output.mkdir(parents=True, exist_ok=True)
    c = Canvas(str(output / "session-correspondence.pdf"), pagesize=(WIDTH, 400),
               invariant=True, initialFontName="Body")
    c.setTitle("Native session correspondences: caller effects and diagnosis cost")
    c.setCreator("");c.chart_height=400;c.chart_labels=[]
    # Row-aligned panels keep both timing methods visible without shifting
    # any time value. Session count is a categorical row shared by (a) and (b).
    aleft,aright,bleft,bright=55,180,244,382
    ax=lambda value:aleft+math.log(value/.8)/math.log(1500/.8)*(aright-aleft)
    unrestricted=[costs[n]["methods"][method+"/unrestricted"]["diagnosis_wall_ns"]
                  for n in range(2,7) for method,_,_ in METHODS]
    b_lower=10**math.floor(math.log10(min(v["minimum"] for v in unrestricted)/1e6))
    b_upper=10**math.ceil(math.log10(max(v["maximum"] for v in unrestricted)/1e6))
    bx=lambda value:bleft+math.log(value/b_lower)/math.log(b_upper/b_lower)*(bright-bleft)
    top,bottom=331,201
    row_y={n:317-24*(n-2) for n in range(2,7)}
    text(c,(aleft+aright)/2,384,"(a) Retained bindings",font="Bold",size=11)
    text(c,(bleft+bright)/2,384,"(b) Unrestricted caller",font="Bold",size=11)
    dot(c,aleft+6,365,2.6,True,INK)
    text(c,aleft+15,361.5,"Lookup only","left",size=10.5)
    diamond(c,aleft+6,348,2.6,INK)
    text(c,aleft+15,344.5,"Removal admitted","left",size=10.5)
    for xx,(method,label,color) in zip((bleft+3,bleft+73),METHODS):
        mark(c,method,xx,365,2.6)
        text(c,xx+8,361.5,label,"left",size=10.5)
    text(c,(bleft+bright)/2,344.5,"Median and seven-run range",size=10)
    for tick in (1,10,100,1000):
        xx=ax(tick);line(c,xx,bottom,xx,top,GRID,.6)
        align = "left" if abs(xx-aleft)<.5 else ("right" if abs(xx-aright)<.5 else "center")
        text(c,xx,187,str(tick),align,size=9.0)
    for tick in (10**exponent for exponent in range(int(math.log10(b_lower)),int(math.log10(b_upper))+1)):
        xx=bx(tick);line(c,xx,bottom,xx,top,GRID,.6)
        align = "left" if abs(xx-bleft)<.5 else ("right" if abs(xx-bright)<.5 else "center")
        text(c,xx,187,f"{tick:g}",align,size=9.0)
    for left,right in ((aleft,aright),(bleft,bright)):line(c,left,bottom,right,bottom,INK,.7)
    text(c,(aleft+aright)/2,169,"Matching bindings (log)",size=10.5)
    text(c,(bleft+bright)/2,169,"Diagnosis time (ms, log)",size=10.5)
    rotated(c,15,(top+bottom)/2,"Sessions")
    for n in range(2,7):
        yy=row_y[n];count=observations[n]["family_members"]
        text(c,42,yy-3.5,str(n),"right",size=10.5)
        line(c,ax(1),yy,ax(count),yy,SECONDARY,1.0)
        diamond(c,ax(1),yy,2.6,INK)
        dot(c,ax(count),yy,2.7,True,INK)
        label_x=ax(count)+7
        label_width=pdfmetrics.stringWidth(str(count),"Body",10)
        rect(c,label_x-1.5,yy-6,label_width+3,11.5,white)
        text(c,label_x,yy-3.5,str(count),"left",size=10)
    for cy in row_y.values():line(c,bleft,cy,bright,cy,GRID,.6)
    timing_rows=[]
    for (method,label,color),offset in zip(METHODS,(4.5,-4.5)):
        for n in range(2,7):
            values=costs[n]["methods"][method+"/unrestricted"]["diagnosis_wall_ns"]
            values_ms={key:value/1e6 for key,value in values.items() if key!="samples"}
            yy=row_y[n]+offset;lo,hi=bx(values_ms['minimum']),bx(values_ms['maximum'])
            if not bleft<=lo<=hi<=bright:raise ValueError("Timing outside fixed axes")
            line(c,lo,yy,hi,yy,color,.9)
            for xx in (lo,hi):line(c,xx,yy-2.0,xx,yy+2.0,color,.8)
            mark(c,method,bx(values_ms['median']),yy,2.7)
            timing_rows.append({"sessions":n,"caller":"unrestricted","method":method,
                                "diagnosis_ms":values_ms,"raw_wall_ns":values["samples"]})
    cleft,cright,cbottom,ctop=131,382,31,131
    detail_max=max(values['diagnosis_wall_ns']['maximum']/1e6 for values in costs[6]['methods'].values())
    detail_step=next(step for step in (1,2,5,10,20,50,100,200,500,1000,2000) if detail_max/step<=5)
    detail_upper=math.ceil(detail_max/detail_step)*detail_step
    cx=lambda value:cleft+value/detail_upper*(cright-cleft)
    text(c,(cleft+cright)/2,145,"(c) Caller language with six sessions",font="Bold",size=11)
    for tick in range(0,detail_upper+1,detail_step):
        xx=cx(tick);line(c,xx,cbottom,xx,ctop,GRID,.6)
        text(c,xx,17,str(tick),size=10)
    line(c,cleft,cbottom,cright,cbottom,INK,.7)
    for caller,label,cy in (("lookup-only","Lookup only",120),
                            ("one-removal","One removal",86),
                            ("unrestricted","Unrestricted",52)):
        text(c,cleft-10,cy-3.5,label,"right",size=10.5)
        for (method,_,color),offset in zip(METHODS,(4.5,-4.5)):
            values=costs[6]["methods"][method+"/"+caller]["diagnosis_wall_ns"]
            values_ms={key:value/1e6 for key,value in values.items() if key!="samples"}
            yy=cy+offset;lo,hi=cx(values_ms['minimum']),cx(values_ms['maximum'])
            if not cleft<=lo<=hi<=cright:raise ValueError("Timing outside detail axes")
            line(c,lo,yy,hi,yy,color,1.0)
            for xx in (lo,hi):line(c,xx,yy-2.2,xx,yy+2.2,color,.8)
            mark(c,method,cx(values_ms['median']),yy,2.7)
            if caller!="unrestricted":
                timing_rows.append({"sessions":6,"caller":caller,"method":method,
                                    "diagnosis_ms":values_ms,"raw_wall_ns":values['samples']})
    text(c,(cleft+cright)/2,5,"Diagnosis time (ms)",size=10.5)
    c.showPage();c.save()

    result={"source":"Native Piccolo session correspondence study; unmodified source arm",
            "scientific_inputs":["results/session-correspondence/diagnosis.json",
                                 "results/symbolic-comparison/summary.json",
                                 "results/symbolic-comparison/trials.json"],
            "timing_summary_recomputed_from_process_records":True,
            "timing_scope":"Diagnosis of already supplied families: input normalization, graph, comparison, indexes and individual witness replays. Native acquisition, permutation enumeration and output serialization are separate.",
            "uncertainty":"Symbols are medians; intervals are observed minima and maxima of seven runs, without a confidence level.",
            "retained_bindings":[{"sessions":n,"supplied_bijections":observations[n]["family_members"],
                                   "caller_outcomes":observations[n]["caller_outcomes"],
                                   "selected_identity_matching":observations[n]["selected_identity_matching"]}
                                  for n in range(2,7)],
            "timings":timing_rows,
            "axes": {"unrestricted_min_ms": b_lower, "unrestricted_max_ms": b_upper,
                     "detail_min_ms": 0, "detail_max_ms": detail_upper},
            "detail_panel_note":"The unrestricted six-session intervals also appear in panel b; panel c adds the other two caller languages."}
    (output/"session-correspondence.json").write_text(json.dumps(result,indent=2)+"\n")
    return result


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results",type=Path,default=DEFAULT_RESULTS)
    parser.add_argument("--comparison-results",type=Path,default=ART / "results/symbolic-comparison")
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args();register_fonts();result=draw(args.results,args.output,args.comparison_results)
    print(json.dumps({"status":"PASS","session_counts":len(result["retained_bindings"]),
                      "timing_series":len(result["timings"])}))
