"""Render a source-backed session accuracy figure from a completed pilot."""
import argparse
import json
from pathlib import Path


def main():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    p = argparse.ArgumentParser()
    p.add_argument('run', type=Path)
    a = p.parse_args()
    metrics = json.loads((a.run/'metrics.json').read_text())
    sessions = metrics['by_session']
    delays = metrics['by_evidence_delay']
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5), gridspec_kw={'width_ratios': [1.35, 1]})
    for arm, label, color in [('baseline', 'Luna: current session only', '#555555'),
                              ('memory', 'Same Luna + Qwen-managed notes', '#0068a0')]:
        x = sorted(map(int, sessions))
        axes[0].plot([i+1 for i in x], [100*sessions[str(i)][arm+'_accuracy'] for i in x],
                     marker='o', linewidth=2, label=label, color=color)
        d = sorted(map(int, delays))
        axes[1].plot(d, [100*delays[str(i)][arm+'_accuracy'] for i in d],
                     marker='o', linewidth=2, color=color)
    axes[0].set(title='Preference recovery at every session', xlabel='Session (1–10)', ylabel='Paired-question accuracy (%)')
    axes[1].set(title='Accuracy by age of latest true evidence', xlabel='Sessions since latest true preference event', ylabel='Paired-question accuracy (%)')
    for ax in axes:
        ax.set_ylim(0, 105)
        ax.grid(axis='y', alpha=.2)
        ax.spines[['top', 'right']].set_visible(False)
    axes[0].set_xticks(range(1, 11))
    axes[0].legend(loc='lower left', frameon=False, fontsize=8)
    axes[1].set_xticks(d, [f'{i}\n(n={delays[str(i)]["questions"]})' for i in d], fontsize=8)
    fig.suptitle('AdaptGym · 10 synthetic users × 10 sessions · fixed Qwen3-1.7B policy', fontsize=13)
    fig.text(.01, .01, 'Source: saved pilot metrics, 17 Sep 2026. Session 1 shares one identical request. Delay does not exclude distractor repetitions. No training.', fontsize=8)
    fig.tight_layout(rect=(0, .05, 1, .94))
    fig.savefig(a.run/'accuracy.png', dpi=180)
    fig.savefig(a.run/'accuracy.svg')


if __name__ == '__main__':
    main()
