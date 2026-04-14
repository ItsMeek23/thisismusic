#!/usr/bin/env python3
import sys
import re
from collections import defaultdict

#This ANSI colors per service as it's easier for visual tracing in the logs
#ANSI colors per service
COLORS = {
    "FE":    "\033[0;32m",   #Color = green
    "BE-FE": "\033[0;34m",   #Color = blue
    "DB":    "\033[0;33m",   #Color = yellow
    "BE-DB": "\033[0;35m",   #Color = purple
}
NC = "\033[0m"
BOLD = "\033[1m"
#The grouped logs can be stored by correlation ID
groups = defaultdict(list)
CORR_RE = re.compile(r'corr[=:]([a-f0-9\-]{36})', re.IGNORECASE)

def color(service, text):
    c = COLORS.get(service, "")
    return f"{c}[{service:<5}]{NC}  {text}"

def handleline(raw):
    if "|" not in raw:
        return
    service, , line = raw.partition("|")
    service = service.strip()
    line = line.rstrip()
    match = CORR_RE.search(line) #this is to check if the line is being tied to a correlation ID
    if not match:
        print(color(service, line))
        sys.stdout.flush()
        return
    corr_id = match.group(1)
    #if this is the first time seeing a request, it will print a header
    if not groups[corr_id]:
        print(f"\n{BOLD}--- corr={corr_id} ---{NC}")
    #This is keepign track of the logs for any sort of request
    groups[corr_id].append((service, line))
    print(color(service, line))
    sys.stdout.flush()

try:
    for raw_line in sys.stdin:
        handle_line(raw_line)
except KeyboardInterrupt:
    print("\nLOGS STOPPED")
    sys.exit(0) 