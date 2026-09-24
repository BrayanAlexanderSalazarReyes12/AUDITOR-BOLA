"""Prueba los cuatro proyectos en copias bajo evidencias/integracion.

Requiere las copias de los proyectos, dependencias Python/Node y Tomcat
preparado por prepare_java_validation.py. No modifica los repositorios fuente.
"""
from pathlib import Path
import json
import os
import socket
import sys
import argparse
import shutil

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from auditor_bola.cli import _resolve_live
from auditor_bola.config import cargar_config
from auditor_bola.profile_builder import detect_project, build_profile_draft, save_profile_draft
from auditor_bola.process_manager import LocalTargetProcess
from auditor_bola.runner import diagnosticar


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", choices=("vulndesk-python", "vulncommerce-node", "vulnport-java", "tramitia-app"))
    args = parser.parse_args()
    work = ROOT / "evidencias/integracion"
    reports = {}
    for name in ("vulndesk-python", "vulncommerce-node", "vulnport-java", "tramitia-app"):
        if args.only and name != args.only:
            continue
        target = work / name
        if not target.exists():
            shutil.copytree(ROOT.parent / name, target, ignore=shutil.ignore_patterns(".git", ".venv", "__pycache__", "node_modules", "instance", "target", ".pytest_cache"))
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        base = f"http://127.0.0.1:{port}"
        detection = detect_project(target)
        profile = build_profile_draft(detection, base_url=base)
        runtime = profile["runtime"]
        runtime.update(preparar_automaticamente=False, alternativas=[], modo="process", timeout_inicio=60)
        if name == "vulndesk-python":
            runtime["comando_inicio"] = [sys.executable, "-c", f"from vulndesk.app import create_app; create_app().run(host='127.0.0.1',port={port})"]
        elif name == "vulncommerce-node":
            runtime["comando_inicio"] = ["node", "src/server.js"]
            runtime["variables"] = {"PORT": str(port), "NODE_PATH": str(ROOT.parent / name / "node_modules")}
        elif name == "tramitia-app":
            runtime["variables"] = {"TRAMITIA_PORT": str(port)}
        else:
            runtime_file = work / "java-runtime/runtime.json"
            tomcat = (work / "java-runtime" / json.loads(runtime_file.read_text())["tomcat"]
                      if runtime_file.exists() else next((work / "java-runtime").glob("apache-tomcat-*")))
            server = tomcat / "conf/server.xml"
            import re
            settings = re.sub(r'address="127.0.0.1" port="\d+"', f'address="127.0.0.1" port="{port}"', server.read_text())
            settings = settings.replace('port="8080"', f'address="127.0.0.1" port="{port}"')
            settings = re.sub(r'<Server port="\d+"', '<Server port="-1"', settings)
            # NIO2 evita el problema del selector Unix-domain de este JDK en Windows.
            settings = settings.replace('protocol="HTTP/1.1"', 'protocol="org.apache.coyote.http11.Http11Nio2Protocol"')
            server.write_text(settings)
            runtime["comando_inicio"] = [
                "java", f"-Dcatalina.home={tomcat}", f"-Dcatalina.base={tomcat}",
                "-cp", os.pathsep.join(str(tomcat / "bin" / jar) for jar in ("bootstrap.jar", "tomcat-juli.jar")),
                "org.apache.catalina.startup.Bootstrap", "start",
            ]
            base += "/vulnport-java"
            profile["base_url"] = base
        runtime["base_url"] = base
        profile_path = work / f"{name}.json"
        save_profile_draft(profile, profile_path)
        cfg = cargar_config(profile_path)
        manager = LocalTargetProcess(target, cfg.runtime, authorized_base_url=base)
        try:
            manager.start()
            # Tomcat abre el socket antes de terminar el despliegue del WAR.
            import time
            import requests
            ready = False
            for _ in range(20):
                if manager.process is not None and manager.process.poll() is not None:
                    raise RuntimeError(manager.runtime_output_tail())
                try:
                    if requests.get(base + "/", timeout=2).status_code != 404:
                        ready = True
                        break
                except requests.RequestException:
                    pass
                time.sleep(0.25)
            if not ready:
                raise RuntimeError("El objetivo no respondió a HTTP: " + manager.runtime_output_tail())
            _resolve_live(cfg)
            cfg.probar_todos_endpoints_con_todos_usuarios = False
            result = diagnosticar(cfg, target)
            (work / f"{name}-resultado.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            assert len(cfg.cuentas) == 3, name
            assert result["resumen"]["bola_confirmados"] >= 1, (name, result["resumen"])
            assert result["resumen"]["errores"] == 0, (name, result["resumen"])
            reports[name] = result["resumen"]
            print(name, json.dumps(result["resumen"]), flush=True)
        finally:
            try:
                (work / f"{name}-runtime.log").write_text(manager.runtime_output_tail(), encoding="utf-8")
            finally:
                manager.stop()
    (work / "resumen.json").write_text(json.dumps(reports, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
