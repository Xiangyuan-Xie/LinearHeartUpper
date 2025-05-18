import os


def count_lines(directory):
    total = 0
    for root, _, files in os.walk(directory):
        for file in files:
            if file.endswith(".py"):
                with open(os.path.join(root, file), "r", encoding="utf-8") as f:
                    lines = [line for line in f if line.strip() and not line.strip().startswith("#")]
                    total += len(lines)
    return total


if __name__ == "__main__":
    print(f"有效代码行数（排除空行和单行注释）: {count_lines('..')}")
