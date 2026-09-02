import sys
sys.stdout.reconfigure(encoding='utf-8')
content = open('agents/base.py', 'r', encoding='utf-8').read()

old = '''        except Exception as e:
            logger.error("[%s] Failed: %s", self.name, e)
            return {"errors": [f"{self.name}: {e}"]}'''

new = '''        except Exception as e:
            import traceback
            logger.error("[%s] Failed: %s\\n%s", self.name, e, traceback.format_exc())
            return {"errors": [f"{self.name}: {e}"]}'''

content = content.replace(old, new)
open('agents/base.py', 'w', encoding='utf-8').write(content)
print("Added traceback to BaseAgent error handler")
