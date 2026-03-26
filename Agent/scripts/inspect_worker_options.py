import inspect
from livekit import agents

print("WorkerOptions signature:")
try:
    print(inspect.signature(agents.WorkerOptions.__init__))
except Exception as e:
    print(e)

print("\nServerOptions signature (if exists):")
try:
    # Assuming WorkerOptions is related?
    pass
except:
    pass

print("\nWorkerOptions dir:")
print(dir(agents.WorkerOptions))






print("\nAgentServer.run source:")
try:
    print(inspect.getsource(agents.AgentServer.run))
except Exception as e:
    print(e)





