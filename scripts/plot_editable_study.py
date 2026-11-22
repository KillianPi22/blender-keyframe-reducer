"""Plot a generated fitting study. Optional matplotlib, not an add-on dependency."""
import argparse
import json
import math
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('comparison', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    data = json.loads(args.comparison.read_text())
    plt.rcParams.update({'text.color': '#eceff3', 'axes.labelcolor': '#c8cdd6',
                         'xtick.color': '#aab2be', 'ytick.color': '#aab2be', 'font.size': 11})
    fig, axes = plt.subplots(2, 2, figsize=(15, 7.8), facecolor='#1b1e24')
    for row, (name, label) in enumerate([('shoulder', 'Épaules et changements de direction'),
                                        ('small_ripple', 'Arc avec petites oscillations')]):
        case = data[name]
        for col, (version, title, color) in enumerate([('1.3', 'Version 1.3', '#ffb454'),
                                                       ('current', 'Version 1.4', '#59d3b6')]):
            ax, result = axes[row, col], case['results'][version]
            ax.set_facecolor('#242930')
            ax.plot([p[0] for p in case['reference']],
                    [math.degrees(p[1]) for p in case['reference']],
                    color='#9da8b5', linewidth=2, alpha=.65, label='Source')
            ax.plot([p[0] for p in result['samples']],
                    [math.degrees(p[1]) for p in result['samples']],
                    color=color, linewidth=1.5, label='Courbe ajustée')
            for key in result['controls']:
                t, v = key['co']
                if col:
                    ax.plot([key['left'][0], t, key['right'][0]],
                            [math.degrees(key['left'][1]), math.degrees(v), math.degrees(key['right'][1])],
                            color=color, linewidth=.75, alpha=.65, marker='o', markersize=2)
                ax.plot(t, math.degrees(v), 'o', color=color, markersize=4.5)
            ax.set_title(f"{title} · {result['keys']} clés", loc='left', pad=12,
                         fontweight='bold', color=color)
            ax.text(.02, .93, label, transform=ax.transAxes, fontsize=10, color='#c3cbd5')
            ax.set_xlabel('Image')
            ax.set_ylabel('Rotation (°)')
            ax.grid(color='#444b56', linewidth=.5, alpha=.5)
            for spine in ax.spines.values():
                spine.set_color('#444b56')
            ax.margins(x=.025, y=.22)
    axes[0, 0].legend(loc='lower right', facecolor='#242930', edgecolor='#444b56', labelcolor='#c8cdd6')
    fig.suptitle('Moins de contrôles, à la même tolérance de 0,5°', fontsize=19, x=.04, ha='left')
    fig.text(.04, .015, 'Courbes générées pour les essais — ce comparatif ne représente pas la scène du Minotaure.',
             color='#9da8b5', fontsize=10)
    fig.tight_layout(rect=(0, .035, 1, .94), h_pad=2.5, w_pad=2.5)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.output, dpi=140, facecolor=fig.get_facecolor())
    print(args.output.resolve())


if __name__ == '__main__':
    main()
