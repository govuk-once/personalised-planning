def read_file_content(filepath: str) -> str:
    try:
        with open(filepath, encoding="utf-8") as f:
            content = f.read()
        return content
    except FileNotFoundError:
        print(f"Error: The file was not found at path: {filepath}")
        return ""
    except Exception as e:
        print(f"An error occurred while reading the file: {e}")
        return ""
