def print_banner():
    try:
        with open('banner.txt', 'r') as file:
            content = file.read()
            print(content)
    except FileNotFoundError:
        print(f"Error: File banner.txt not found.")
