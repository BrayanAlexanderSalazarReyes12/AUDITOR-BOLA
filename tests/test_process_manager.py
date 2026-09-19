from pathlib import Path
from unittest.mock import patch
import signal

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

    with patch("auditor_bola.process_manager._is_windows", return_value=True), patch(
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

    assert command[:5] == [
        r"C:\Windows\System32\cmd.exe",
        "/d",
        "/s",
        "/c",
        "call",
    ]
    assert command[5] == r"C:\Program Files\nodejs\npm.cmd"
    assert command[6:] == ["start"]


def test_windows_resuelve_launcher_local_gradlew_bat(tmp_path):
    launcher = tmp_path / "gradlew.bat"
    launcher.write_text("@echo off\n", encoding="utf-8")
    manager = _manager(tmp_path, ["gradlew", "bootRun"])

    with patch("auditor_bola.process_manager._is_windows", return_value=True), patch(
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

    assert command[:5] == [
        r"C:\Windows\System32\cmd.exe",
        "/d",
        "/s",
        "/c",
        "call",
    ]
    assert command[5].lower().endswith("gradlew.bat")
    assert command[6:] == ["bootRun"]


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


def test_selecciona_comando_especifico_para_windows(tmp_path):
    runtime = RuntimeConfig(
        comando_inicio=["python", "fallback.py"],
        comando_inicio_por_so={
            "windows": ["npm", "start"],
            "linux": ["bash", "start.sh"],
            "macos": ["bash", "start-macos.sh"],
        },
        espera_inicio=0,
    )
    manager = LocalTargetProcess(tmp_path, runtime)

    with patch("auditor_bola.process_manager._is_windows", return_value=True):
        assert manager._command_for("inicio") == ["npm", "start"]


def test_selecciona_comando_especifico_para_macos(tmp_path):
    runtime = RuntimeConfig(
        comando_inicio=["python", "fallback.py"],
        comando_inicio_por_so={
            "macos": ["php", "-S", "127.0.0.1:8080"],
        },
        espera_inicio=0,
    )
    manager = LocalTargetProcess(tmp_path, runtime)

    with patch("auditor_bola.process_manager._is_windows", return_value=False), patch(
        "auditor_bola.process_manager.sys.platform",
        "darwin",
    ):
        assert manager._command_for("inicio") == [
            "php",
            "-S",
            "127.0.0.1:8080",
        ]


def test_service_mode_usa_comandos_de_control(tmp_path):
    runtime = RuntimeConfig(
        modo="service",
        comando_inicio=["docker", "compose", "up", "-d"],
        comando_detener=["docker", "compose", "down"],
        espera_inicio=0,
    )
    manager = LocalTargetProcess(tmp_path, runtime)

    with patch.object(manager, "_run_control_command") as run:
        manager.start()
        assert manager.is_running() is True
        run.assert_called_once_with(
            ["docker", "compose", "up", "-d"],
            action_name="iniciar",
        )

        run.reset_mock()
        manager.stop()
        assert manager.is_running() is False
        run.assert_called_once_with(
            ["docker", "compose", "down"],
            action_name="detener",
        )


def test_external_mode_no_intenta_arrancar(tmp_path):
    runtime = RuntimeConfig(modo="external")
    manager = LocalTargetProcess(tmp_path, runtime)

    with pytest.raises(RuntimeError) as exc:
        manager.start()

    assert "external" in str(exc.value)


def test_preparacion_automatica_se_ejecuta_una_sola_vez(tmp_path):
    runtime = RuntimeConfig(
        comando_inicio=["python", "app.py"],
        preparar_automaticamente=True,
        comandos_preparacion=[
            ["npm", "install"],
            ["npm", "run", "build"],
        ],
        espera_inicio=0,
    )
    manager = LocalTargetProcess(tmp_path, runtime)

    with patch.object(manager, "_run_control_command") as run:
        manager._prepare_if_needed()
        manager._prepare_if_needed()

    assert run.call_count == 2
    assert manager._prepared is True


def test_error_de_arranque_incluye_salida_real_del_proceso(tmp_path):
    script = tmp_path / "fail.py"
    script.write_text(
        "import sys\nprint('ERROR_DE_PRUEBA')\nsys.exit(1)\n",
        encoding="utf-8",
    )

    runtime = RuntimeConfig(
        comando_inicio=[str(script)],
        espera_inicio=0.2,
    )
    manager = LocalTargetProcess(tmp_path, runtime)

    with pytest.raises(RuntimeError) as exc:
        manager.start()

    assert "código 1" in str(exc.value)
    assert "ERROR_DE_PRUEBA" in str(exc.value)


def test_windows_cmd_no_preescapa_comillas_de_ruta(tmp_path):
    manager = _manager(tmp_path, ["npm", "install", "--no-audit"])

    def fake_which(name, path=None):
        if name == "npm":
            return r"C:\Program Files\nodejs\npm.CMD"
        return None

    with patch("auditor_bola.process_manager._is_windows", return_value=True), patch(
        "auditor_bola.process_manager.shutil.which",
        side_effect=fake_which,
    ):
        command = manager._resolver_comando(
            tmp_path,
            {
                "PATH": r"C:\Program Files\nodejs",
                "COMSPEC": r"C:\Windows\System32\cmd.exe",
            },
        )

    assert command == [
        r"C:\Windows\System32\cmd.exe",
        "/d",
        "/s",
        "/c",
        "call",
        r"C:\Program Files\nodejs\npm.CMD",
        "install",
        "--no-audit",
    ]
    assert all('\\"' not in part for part in command)


def test_windows_detiene_arbol_completo_con_taskkill(tmp_path):
    runtime = RuntimeConfig(comando_inicio=["npm", "start"], espera_inicio=0)
    manager = LocalTargetProcess(tmp_path, runtime)

    class FakeProcess:
        pid = 4321
        def poll(self):
            return None
        def wait(self, timeout=None):
            return 0
        def terminate(self):
            raise AssertionError("no debe usar terminate si taskkill funciona")
        def kill(self):
            raise AssertionError("no debe usar kill si taskkill funciona")

    manager.process = FakeProcess()

    completed = type("Completed", (), {"returncode": 0})()

    with patch("auditor_bola.process_manager._is_windows", return_value=True), patch(
        "auditor_bola.process_manager.subprocess.run",
        return_value=completed,
    ) as run:
        manager._terminate_process_tree()

    run.assert_called_once()
    command = run.call_args.args[0]
    assert command == ["taskkill", "/PID", "4321", "/T", "/F"]


def test_posix_detiene_grupo_de_procesos(tmp_path):
    runtime = RuntimeConfig(comando_inicio=["python", "app.py"], espera_inicio=0)
    manager = LocalTargetProcess(tmp_path, runtime)

    class FakeProcess:
        pid = 9876
        def poll(self):
            return None
        def wait(self, timeout=None):
            return 0

    manager.process = FakeProcess()

    with patch("auditor_bola.process_manager._is_windows", return_value=False), patch(
        "auditor_bola.process_manager.os.getpgid",
        return_value=9876,
    ), patch(
        "auditor_bola.process_manager.os.killpg"
    ) as killpg:
        manager._terminate_process_tree()

    killpg.assert_called_once_with(9876, signal.SIGTERM)
