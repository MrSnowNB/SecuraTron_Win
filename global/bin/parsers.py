import xml.etree.ElementTree as ET
import json
import re

PARSERS = {}

def register(type_name):
    def deco(fn):
        PARSERS[type_name] = fn
        return fn
    return deco

@register("shell.run.v1")
def parse_shell_run(raw_stdout, raw_stderr, exit_code, **kwargs):
    return {
        "stdout": raw_stdout,
        "stderr": raw_stderr,
        "exit_code": exit_code,
        "duration_ms": kwargs.get("duration_ms", 0)
    }

@register("fs.read.v1")
def parse_fs_read(raw_stdout, **kwargs):
    return {
        "path": kwargs.get("inputs", {}).get("path", "unknown"),
        "content": raw_stdout,
        "encoding": "utf-8",
        "size": len(raw_stdout.encode("utf-8"))
    }

@register("nmap.scan.v1")
def parse_nmap_scan(raw_stdout, **kwargs):
    """Parse nmap XML output into structured hosts/ports list."""
    try:
        # Nmap -oX - sends XML to stdout
        root = ET.fromstring(raw_stdout)
        hosts = []
        
        for host in root.findall("host"):
            ip = host.find("address").get("addr")
            ports = []
            
            for port in host.findall("ports/port"):
                ports.append({
                    "port": int(port.get("portid")),
                    "protocol": port.get("protocol"),
                    "service": port.find("service").get("name") if port.find("service") is not None else "unknown",
                    "state": port.find("state").get("state")
                })
                
            hosts.append({"ip": ip, "ports": ports})
            
        return {"hosts": hosts}
    except Exception as e:
        return {"error": f"xml_parse_failure: {str(e)}", "raw": raw_stdout[:500]}

@register("whatweb.fingerprint.v1")
def parse_whatweb_fingerprint(raw_stdout, **kwargs):
    """Parse WhatWeb JSON output from stdout."""
    # WhatWeb with --log-json /dev/stdout often appends a brief line after the JSON array
    # We find the JSON array part [...]
    try:
        match = re.search(r"(\[.*\])", raw_stdout, re.DOTALL)
        if not match:
            return {"error": "no_json_array_found", "raw": raw_stdout[:500]}
            
        fingerprints = json.loads(match.group(1))
        
        # Primary result is typically the first entry in the array
        primary = fingerprints[0] if fingerprints else {}
        
        return {
            "fingerprints": fingerprints,
            "status_code": primary.get("http_status"),
            "target": primary.get("target"),
            "raw": raw_stdout
        }
    except Exception as e:
        return {"error": f"json_parse_failure: {str(e)}", "raw": raw_stdout[:500]}

def parse(type_name, raw_stdout, **kwargs):
    """Entry point for parsing raw output into structured data."""
    if type_name not in PARSERS:
        return {"ok": True, "raw": raw_stdout} # Fallback
    
    try:
        parsed = PARSERS[type_name](raw_stdout, **kwargs)
        return {"ok": True, "result": parsed}
    except Exception as e:
        return {"ok": False, "reason": "parsing_exception", "error": str(e)}
