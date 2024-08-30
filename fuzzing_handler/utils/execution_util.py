import os
import sys
import shlex
import signal
import subprocess

class ExecutionUtil:
    def __init__(self):
        return

    def executeCommand(self, cmd, timeout=3, env={}):
        stdout, ret_code = None, None

        if " < " in cmd or " > " in cmd:
            p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, preexec_fn=os.setsid, encoding="cp850", universal_newlines=True, env=env, text=True, shell=True)
        else:
            args = shlex.split(cmd)
            p = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, preexec_fn=os.setsid, encoding="cp850", universal_newlines=True, env=env, text=True)

        try:
            stdout, _ = p.communicate(input='y\n', timeout=timeout)
            ret_code = p.returncode
        except subprocess.TimeoutExpired:
            os.killpg(p.pid, signal.SIGTERM)
            try:
                stdout, _ = p.communicate(timeout=2)
                ret_code = p.returncode
            except subprocess.TimeoutExpired:
                os.killpg(p.pid, signal.SIGKILL)
                stdout, _ = p.communicate()
                ret_code = p.returncode
            except Exception as e:
                print(f"[x] Fail to kill the subprocess: {e}")
        except subprocess.SubprocessError as e:
            print(e.cmd)

        return stdout, ret_code
    
    # signum, frame are implicitly invoked
    def cleanupSubprocesses(self, signum=None, frame=None):
        os.killpg(0, signal.SIGTERM)
        if signum is not None:
            sys.exit()

    def registerSignalEvent(self):
        signal.signal(signal.SIGINT, self.cleanupSubprocesses)
        signal.signal(signal.SIGTERM, self.cleanupSubprocesses)

        return
