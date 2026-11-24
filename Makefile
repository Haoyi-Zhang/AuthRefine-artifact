# AuthRefine artifact entry points.  Run from this directory.
# Every target writes into a fresh directory below $(EVIDENCE); remove it
# (make clean) before re-running a target.

PYTHON ?= python3
EVIDENCE ?= /tmp/authrefine-evidence

.PHONY: all review review-extended core portable campaign framework query proofs full references depth figures paper clean

all: review

review:
	$(PYTHON) -B review.py --scope core --output "$(EVIDENCE)/review"

review-extended:
	$(PYTHON) -B review.py --scope extended --output "$(EVIDENCE)/review-extended"

core:
	$(PYTHON) -B evaluate.py --profile core --output "$(EVIDENCE)/core"

portable:
	$(PYTHON) -B evaluate.py --profile portable --output "$(EVIDENCE)/portable"

campaign:
	$(PYTHON) -B run_campaign.py --output "$(EVIDENCE)/campaign"

framework:
	$(PYTHON) -B evaluate.py --profile framework --output "$(EVIDENCE)/framework"

query:
	$(PYTHON) -B evaluate.py --profile query --output "$(EVIDENCE)/query"

proofs:
	$(PYTHON) -B evaluate.py --profile proofs --output "$(EVIDENCE)/proofs"

full:
	$(PYTHON) -B evaluate.py --profile full --output "$(EVIDENCE)/full"

references:
	cd references && $(PYTHON) -B verify.py

depth:
	$(PYTHON) -B verify_research_depth.py --output "$(EVIDENCE)/research-depth.json"

figures:
	$(PYTHON) -B figures/build_paper_figures.py --output-directory "$(EVIDENCE)/figures"

# The manuscript sources are not part of this repository; this target only
# works when they are placed next to it as ../paper/.
paper:
	@test -d ../paper || { echo "make paper: manuscript sources not found in ../paper/"; exit 2; }
	cd ../paper && $(PYTHON) -B build.py --targets main submission supplement

clean:
	rm -rf "$(EVIDENCE)"
