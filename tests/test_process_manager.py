from pathlib import Path
from unittest.mock import patch

import pytest

from auditor_bola.config import RuntimeConfig
from auditor_bola.process_manager import LocalTargetProcess


def _manager(tmp_path: Path, command: list[str]) -> LocalTargetProcess:
    runtime = RuntimeConfig(
        comando_inicio=command,
        directorio_trabajo=".",
        espera_inicio=0,
    )
    return LocalTargetProcess(tmp_path, runtime)


def test_resuelve_ejecutable_normal_desde_path(tmp_path):
    manager = _manager(tmp_path, ["python", "app.py"])

    with patch(
        "auditor_bola.process_manager.shutil.which",
        return_value="/usr/bin/python",
    ):
        command = manager._resolver_comando(tmp_path, {"PATH": "/usr/bin"})

    assert command == ["/usr/bin/python", "app.py"]


def test_windows_envuelve_archivo_cmd_con_cmd_exe(tmp_path):
    manager = _manager(tmp_path, ["npm", "start"])

    def fake_which(name, path=None):
        if name == "npm":
            return r"C:\Program Files\nodejs\npm.cmd"
        if name == "cmd.exe":
            return r"C:\Windows\System32\cmd.exe"
        return None

    with patch("auditor_bola.process_manager.os.name", "nt"), patch(
        "auditor_bola.process_manager.shutil.which",
        side_effect=fake_which,
    ):
        command = manager._resolver_comando(
            tmp_path,
            {
                "PATH": r"C:\Program Files\nodejs;C:\Windows\System32",
                "COMSPEC": r"C:\Windows\System32\cmd.exe",
            },
        )

    assert command[:4] == [
        r"C:\Windows\System32\cmd.exe",
        "/d",
        "/s",
        "/c",
    ]
    assert "npm.cmd" in command[4]
    assert "start" in command[4]


def test_windows_resuelve_launcher_local_gradlew_bat(tmp_path):
    launcher = tmp_path / "gradlew.bat"
    launcher.write_text("@echo off\n", encoding="utf-8")
    manager = _manager(tmp_path, ["gradlew", "bootRun"])

    with patch("auditor_bola.process_manager.os.name", "nt"), patch(
        "auditor_bola.process_manager.shutil.which",
        return_value=None,
    ):
        command = manager._resolver_comando(
            tmp_path,
            {
                "PATH": "",
                "PATHEXT": ".COM;.EXE;.BAT;.CMD",
                "COMSPEC": r"C:\Windows\System32\cmd.exe",
            },
        )

    assert command[:4] == [
        r"C:\Windows\System32\cmd.exe",
        "/d",
        "/s",
        "/c",
    ]
    assert "gradlew.bat" in command[4]
    assert "bootRun" in command[4]


def test_script_python_local_usa_interprete_actual(tmp_path):
    script = tmp_path / "run.py"
    script.write_text("print('ok')\n", encoding="utf-8")
    manager = _manager(tmp_path, ["run.py", "--demo"])

    with patch(
        "auditor_bola.process_manager.shutil.which",
        return_value=None,
    ):
        command = manager._resolver_comando(tmp_path, {"PATH": ""})

    assert command[0]
    assert command[1] == str(script.resolve())
    assert command[2:] == ["--demo"]


def test_jar_local_se_ejecuta_con_java(tmp_path):
    jar = tmp_path / "app.jar"
    jar.write_bytes(b"demo")
    manager = _manager(tmp_path, ["app.jar", "--server.port=9000"])

    def fake_which(name, path=None):
        if name == "java":
            return "/usr/bin/java"
        return None

    with patch(
        "auditor_bola.process_manager.shutil.which",
        side_effect=fake_which,
    ):
        command = manager._resolver_comando(tmp_path, {"PATH": "/usr/bin"})

    assert command == [
        "/usr/bin/java",
        "-jar",
        str(jar.resolve()),
        "--server.port=9000",
    ]


def test_error_claro_si_comando_no_existe(tmp_path):
    manager = _manager(tmp_path, ["herramienta-inexistente", "start"])

    with patch(
        "auditor_bola.process_manager.shutil.which",
        return_value=None,
    ):
        with pytest.raises(FileNotFoundError) as exc:
            manager._resolver_comando(tmp_path, {"PATH": ""})

    assert "herramienta-inexistente" in str(exc.value)
    assert "PATH" in str(exc.value)
