import sys, types
class MockModule(types.ModuleType):
    def __getattr__(self, name):
        return MockModule(name)
    def __call__(self, *args, **kwargs):
        return MockModule("call")
sys.modules['asyncpg'] = MockModule('asyncpg')
sys.modules['sqlalchemy.ext.asyncio'] = MockModule('asyncio')
sys.modules['cv2'] = MockModule('cv2')
sys.modules['ffmpeg'] = MockModule('ffmpeg')

try:
    import app.main
    print("ALL IMPORTS SUCCESSFUL")
except Exception as e:
    import traceback
    traceback.print_exc()
