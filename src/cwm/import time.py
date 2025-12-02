import time
import keyboard
from rich.console import Console
from rich.live import Live
from rich.table import Table

console = Console()

WIDTH = 20
HEIGHT = 10

snake = [(5, 5)]
direction = (0, 1)  # (row, col)
food = (3, 7)


def draw_board():
    table = Table(show_header=False, padding=0, show_lines=False, box=None)

    for r in range(HEIGHT):
        row = ""
        for c in range(WIDTH):
            if (r, c) == food:
                row += "🍎"
            elif (r, c) in snake:
                row += "🟩"
            else:
                row += "⬛"
        table.add_row(row)

    return table


def update_direction():
    global direction
    if keyboard.is_pressed("up"):
        direction = (-1, 0)
    elif keyboard.is_pressed("down"):
        direction = (1, 0)
    elif keyboard.is_pressed("left"):
        direction = (0, -1)
    elif keyboard.is_pressed("right"):
        direction = (0, 1)


def move_snake():
    global snake
    head = snake[0]
    new_head = (head[0] + direction[0], head[1] + direction[1])
    snake.insert(0, new_head)
    snake.pop()


def hit_wall_or_self():
    head = snake[0]
    return (
        head[0] < 0
        or head[0] >= HEIGHT
        or head[1] < 0
        or head[1] >= WIDTH
        or head in snake[1:]
    )


def main():
    with Live(draw_board(), refresh_per_second=10) as live:
        while True:
            update_direction()
            move_snake()

            if hit_wall_or_self():
                console.print("[red bold]GAME OVER![/]")
                break

            live.update(draw_board())
            time.sleep(0.15)


if __name__ == "__main__":
    main()
