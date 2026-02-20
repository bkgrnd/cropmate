import sys

while True:
  what = input("cowsay > ")
  if what != "pengu":
    print(f"Moo moo moo {what} moo")
  else:
    print("bye")
    sys.exit()
