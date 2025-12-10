#!/usr/bin/env python3
import sys
import subprocess

def run_command():
    # Run the daily brief and print constraint stack + UQI
    try:
        result = subprocess.run([sys.executable, 'CHAINWALK_DAILY_BRIEF.py'], capture_output=True, text=True, cwd='.')
        print("Today's Constraint Stack + UQI:")
        # Extract relevant parts, for now print all
        print(result.stdout)
    except Exception as e:
        print(f"Error: {e}")

def post_command():
    # Output Twitter/X template
    print("Twitter/X Template:")
    print("ChainWalk Daily: CTI 5.2 (neutral), MTI 0.4 (strained), IRQ 0.3 (primed), REI 0.4 (charged), UQI 0.3 (imminent). #Bitcoin #ChainWalk")

def tape_command(days=7):
    # Print compression tape
    print(f"Compression Tape for {days} days:")
    print("Day 1: Compression 0.5")
    print("Day 2: Compression 0.6")
    # etc.

def legend_command():
    # Print glyph meanings
    print("Glyph Meanings:")
    print("🟦 Reversible")
    print("🟧 Primed")
    print("🟥 Irreversible")
    print("⚫ Terminal")

def faq_command():
    # Print Sovereign Oracle FAQ
    print("Sovereign Oracle FAQ:")
    print("Q: What is ChainWalk?")
    print("A: A measurement oracle for Bitcoin incentives.")
    print("Q: Why no price?")
    print("A: To avoid influence and ensure sovereignty.")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: chainwalk <command>")
        sys.exit(1)

    command = sys.argv[1]
    if command == "run":
        run_command()
    elif command == "post":
        post_command()
    elif command == "tape":
        days = int(sys.argv[2]) if len(sys.argv) > 2 else 7
        tape_command(days)
    elif command == "legend":
        legend_command()
    elif command == "faq":
        faq_command()
    else:
        print("Unknown command")