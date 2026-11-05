#!/usr/bin/env python3
"""
HomeBank Cash Flow Forecast Engine
==================================
Author: George M. Jones 
Assistant: Gemini 2.5 Flash (Google AI)

Description:
An open-source utility designed to parse native HomeBank (.xhb) XML transaction
archives, extract scheduled templates (<fav> tags) and actual operations (<ope>),
and project future account balances with absolute dated statement anchors.

For the homebamk software see: https://www.gethomebank.org/en/index.php

SPDX-License-Identifier: GPL-3.0-or-later
Copyright (C) 2026 George M Jones

This program is free software: you can redistribute it and/or
modify it under the terms of the GNU General Public License as
published by the Free Software Foundation, either version 3 of
the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program. If not, see <https://www.gnu.org/licenses/>.

"""

import os
import json
import re
import argparse
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta
from collections import defaultdict
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

# Global configuration storage file layout name
CONFIG_FILE = "forecast_config.json"

def load_or_create_config(xml_file_path, filter_patterns=None, force_reconfigure=False):
    """
    Manages operational parameter mapping states. Checks for a cached configuration 
    JSON index and safely falls back to a structural parsing wizard if requested or missing.
    """
    if not os.path.exists(xml_file_path):
        print(f"Error: HomeBank target repository tracking file '{xml_file_path}' not found.")
        return None

    # Step 1: Read structural balance sheets baseline straight from the XML nodes
    tree = ET.parse(xml_file_path)
    root = tree.getroot()
    
    available_accounts = {}
    for acc in root.findall('account'):
        acc_id = acc.get('key')
        name = acc.get('name')
        initial = float(acc.get('initial', 0) or 0)
        available_accounts[acc_id] = {"name": name, "initial": initial}

    # Step 2: Use cached parameters if structural override limits are not explicitly set
    if os.path.exists(CONFIG_FILE) and not force_reconfigure:
        try:
            with open(CONFIG_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Warning: Configuration read fault recovery triggered ({e}). Re-initializing layout engine...")

    print("\n" + "="*60)
    print("        HOMEBANK FORECAST ENGINE MANAGEMENT CONFIGURATION WIZARD")
    print("="*60)
    print("Configure simulation balance layers. Press ENTER to select bracket defaults.\n")
    
    tracked_accounts = {}
    compiled_regexes = [re.compile(p, re.IGNORECASE) for p in filter_patterns] if filter_patterns else []

    # Step 3: Iterate accounts and map inclusion masks
    today_str = date.today().isoformat()
    for acc_id, info in available_accounts.items():
        auto_include = any(rx.search(info['name']) for rx in compiled_regexes)
        
        if auto_include:
            print(f"Pattern match verified! Auto-tracking account category identifier: '{info['name']}'")
            bal_input = input(f"  Enter current starting balance [Default File Balance: {info['initial']}]: ").strip()
            starting_balance = float(bal_input) if bal_input else info['initial']
            date_input = input(f"  Enter as-of date for this balance (YYYY-MM-DD) [Default: {today_str}]: ").strip()
            as_of_date = date_input if date_input else today_str
            tracked_accounts[acc_id] = {"name": info["name"], "starting_balance": starting_balance, "as_of_date": as_of_date}
        else:
            include = input(f"Include account target tracking parameter '{info['name']}'? [y/N]: ").strip().lower()
            if include == 'y':
                bal_input = input(f"  Enter current starting balance [Default File Balance: {info['initial']}]: ").strip()
                starting_balance = float(bal_input) if bal_input else info['initial']
                date_input = input(f"  Enter as-of date for this balance (YYYY-MM-DD) [Default: {today_str}]: ").strip()
                as_of_date = date_input if date_input else today_str
                tracked_accounts[acc_id] = {"name": info["name"], "starting_balance": starting_balance, "as_of_date": as_of_date}
            
    days_input = input("\nSet target timeline duration window index constraint (Days) [Default: 90]: ").strip()
    days_to_forecast = int(days_input) if days_input else 90

    config_data = {
        "days_to_forecast": days_to_forecast,
        "tracked_accounts": tracked_accounts
    }

    with open(CONFIG_FILE, 'w') as f:
        json.dump(config_data, f, indent=4)
    print(f"\nConfiguration parameter matrix successfully saved to local schema path '{CONFIG_FILE}'.")
    return config_data

def _matches_tags(tags_str, filter_tags):
    """Return True if any filter tag is a substring of any transaction tag (case-insensitive)."""
    if not filter_tags:
        return True
    if not tags_str:
        return False
    tx_tags = [t.strip() for t in tags_str.split(',')]
    for f in filter_tags:
        fl = f.lower()
        for t in tx_tags:
            if fl in t.lower():
                return True
    return False

def generate_graph(daily_balances, account_names, show_month_end_only=False, timeline_data=None):
    """
    Renders timeline balances. Custom-tailored to label x-axis strictly monthly, 
    and plot markers only on days where the balance actually changed.
    Hover over any marker to see the transactions that occurred on that day.
    """
    plt.figure(figsize=(12, 6))
    ax = plt.gca()
    
    sorted_dates = sorted(daily_balances.keys())
    timeline_data = timeline_data or {}
    
    # Storage for all plotted points: (artist, xdata, ydata, info_texts)
    plotted_points = []

    if show_month_end_only:
        month_groups = defaultdict(list)
        for d in sorted_dates:
            month_key = date(d.year, d.month, 1)
            month_groups[month_key].append(d)
        
        plot_dates = []
        plot_data = defaultdict(list)
        for m_key in sorted(month_groups.keys()):
            last_date_of_month = max(month_groups[m_key])
            plot_dates.append(last_date_of_month)
            for acc_id, name in account_names.items():
                plot_data[acc_id].append(daily_balances[last_date_of_month][acc_id])
                
        for acc_id, name in account_names.items():
            line, = plt.plot(plot_dates, plot_data[acc_id], marker='o', linewidth=2, label=name)
            for i, d in enumerate(plot_dates):
                info = _build_hover_text(d, acc_id, name, plot_data[acc_id][i], timeline_data)
                plotted_points.append((d, plot_data[acc_id][i], info))
    else:
        for acc_id, name in account_names.items():
            x_dates = []
            y_balances = []
            last_val = None
            for i, d in enumerate(sorted_dates):
                current_val = daily_balances[d][acc_id]
                if i == 0 or i == len(sorted_dates) - 1 or current_val != last_val:
                    x_dates.append(d)
                    y_balances.append(current_val)
                last_val = current_val
                
            line, = plt.plot(x_dates, y_balances, marker='o', linewidth=2, drawstyle='steps-post', label=name)
            for d, bal in zip(x_dates, y_balances):
                info = _build_hover_text(d, acc_id, name, bal, timeline_data)
                plotted_points.append((d, bal, info))

    # Configure axes, zero line, shading (existing code)
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %Y'))
    
    ylim = ax.get_ylim()
    new_bottom = min(ylim[0], 0)
    new_top = max(ylim[1], 0)
    ax.set_ylim(bottom=new_bottom, top=new_top)
    ax.axhline(0, color='red', linewidth=2, linestyle='-', alpha=0.8, label='Zero Balance')
    ax.axhspan(0, new_bottom, facecolor='red', alpha=0.1)

    plt.title("Projected Portfolio Flow Allocation Balances", fontsize=13, fontweight='bold')
    plt.xlabel("Timeline Horizon Intervals", fontsize=10)
    plt.ylabel("Projected System Liquid Currency Worth Value ($)", fontsize=10)
    plt.grid(True, linestyle=':', alpha=0.5)
    plt.legend(loc="upper left", frameon=True, shadow=True)
    plt.gcf().autofmt_xdate()
    plt.tight_layout()

    # --- Interactive hover annotation ---
    annotation = ax.annotate("",
                             xy=(0, 0),
                             xytext=(12, 12),
                             textcoords='offset points',
                             bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.9),
                             arrowprops=dict(arrowstyle='->', color='black'),
                             zorder=10)
    annotation.set_visible(False)

    def _hover(event):
        if event.inaxes != ax:
            annotation.set_visible(False)
            plt.draw()
            return

        # Transform data points to display coordinates for fast distance check
        closest = None
        min_dist = float('inf')
        threshold = 10  # pixels

        for x_d, y_val, info in plotted_points:
            # Convert data point to display coordinates
            disp_x, disp_y = ax.transData.transform((mdates.date2num(x_d), y_val))
            # Mouse event already in display coords
            dist = ((event.x - disp_x) ** 2 + (event.y - disp_y) ** 2) ** 0.5
            if dist < min_dist:
                min_dist = dist
                closest = (x_d, y_val, info)

        if closest and min_dist <= threshold:
            x_d, y_val, info = closest
            annotation.xy = (mdates.date2num(x_d), y_val)
            annotation.set_text(info)
            annotation.set_visible(True)
            plt.draw()
        else:
            annotation.set_visible(False)
            plt.draw()

    ax.figure.canvas.mpl_connect('motion_notify_event', _hover)
    # Optional: also handle click events (pin the annotation)
    def _click(event):
        if event.inaxes == ax:
            _hover(event)  # Reuse the same logic – click acts as a "hover"
    ax.figure.canvas.mpl_connect('button_press_event', _click)

    print("\nDisplaying balance trend visualization map... Hover over any marker to see transaction details.")
    plt.show()

def _build_hover_text(day, acc_id, account_name, balance, timeline_data):
    """
    Creates the tooltip text for a specific point on the graph.
    Shows the date, account, balance, and any transactions that occurred that day.
    """
    lines = [f"Date: {day.isoformat()}",
             f"Account: {account_name}",
             f"Balance: ${balance:,.2f}"]
    
    txs = timeline_data.get(day, [])
    if any(tx.get('src_acc') == acc_id or tx.get('dst_acc') == acc_id for tx in txs):
        lines.append("")
        lines.append("Transactions:")
        for tx in txs:
            src_id, dst_id = tx['src_acc'], tx['dst_acc']
            amount = tx['amount']
            desc = tx.get('wording', '')
            tags = tx.get('tags', '')
            tag_str = f" [tags: {tags}]" if tags else ""
            if src_id == acc_id and dst_id:
                lines.append(f"  TRSF OUT: -${abs(amount):,.2f} {desc}{tag_str}")
            elif dst_id == acc_id and src_id:
                lines.append(f"  TRSF IN: +${abs(amount):,.2f} {desc}{tag_str}")
            elif src_id == acc_id:
                lines.append(f"  DEBIT: -${abs(amount):,.2f} {desc}{tag_str}")
            elif dst_id == acc_id:
                lines.append(f"  CREDIT: +${abs(amount):,.2f} {desc}{tag_str}")
    return "\n".join(lines)

def run_forecast(xml_file_path, filter_patterns, force_reconfigure, start_date_str, end_date_str, days_horizon, show_month_end, filter_tags=None):
    """
    Main execution pipeline. Parses database structures, builds clean timelines,
    and runs simulation logs with historical tracking alignment safeguards.
    """
    config = load_or_create_config(xml_file_path, filter_patterns, force_reconfigure)
    if not config or not config["tracked_accounts"]:
        print("Error: Operational context initialization tracking parameters array null. Exiting pipeline.")
        return

    # Parse runtime dynamic dates constraints parameters
    start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date() if start_date_str else date.today()
    
    if end_date_str:
        end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date()
    elif days_horizon:
        end_date = start_date + timedelta(days=days_horizon)
    else:
        end_date = start_date + timedelta(days=config["days_to_forecast"])

    # Compile regex runtime target mask
    compiled_regexes = [re.compile(p, re.IGNORECASE) for p in filter_patterns] if filter_patterns else []
    
    # Compile tag filters into a set for fast lookup
    filter_tags = [t.strip() for t in filter_tags] if filter_tags else []
    
    tracked_ids = []
    balances = {}
    account_names = {}
    account_as_of = {}

    for acc_id, data in config["tracked_accounts"].items():
        # Match against active operational filtering rules
        if compiled_regexes and not any(rx.search(data["name"]) for rx in compiled_regexes):
            continue
        tracked_ids.append(acc_id)
        balances[acc_id] = data["starting_balance"]
        account_names[acc_id] = data["name"]
        account_as_of[acc_id] = datetime.strptime(data["as_of_date"], "%Y-%m-%d").date()

    if not tracked_ids:
        print("No accounts match runtime regular expression filters.")
        return

    tree = ET.parse(xml_file_path)
    root = tree.getroot()
    
    timeline = defaultdict(list)
    historical_delta = defaultdict(float)

    # Helper lambda to parse integers safely out of HomeBank's custom date representation
    parse_hb_date = lambda d_str: date.fromordinal(int(d_str)) if d_str else None

    # Step A: Process Actual Standard Operations (<ope>)
    for ope in root.findall('ope'):
        ope_date = parse_hb_date(ope.get('date'))
        if not ope_date: continue
        
        # Tag filter check
        if not _matches_tags(ope.get('tags', ''), filter_tags):
            continue

        seen_kxfer = set()
        if ope.get('dst_account'):
            # Skip the positive mirror row (the "deposit-looking" duplicate)
            if float(ope.get('amount', 0)) > 0:
                continue
            # Also skip any second copy that has the same kxfer
            kxfer = ope.get('kxfer')
            if kxfer:
                if kxfer in seen_kxfer:
                    continue
                seen_kxfer.add(kxfer)
        
        amount = float(ope.get('amount', 0))
        src_acc = ope.get('account')
        dst_acc = ope.get('dst_account')

        # Apply strict source accounting checks
        if src_acc in tracked_ids and ope_date > account_as_of[src_acc]:
            if ope_date < start_date:
                historical_delta[src_acc] += amount
            elif ope_date <= end_date:
                timeline[ope_date].append({'amount': amount, 'src_acc': src_acc, 'dst_acc': dst_acc, 'wording': ope.get('wording', ''), 'tags': ope.get('tags', '')})
                
        if dst_acc in tracked_ids and ope_date > account_as_of[dst_acc]:
            if ope_date < start_date:
                historical_delta[dst_acc] -= amount # Received transfers add balance inversely in ledger rules
            elif ope_date <= end_date:
                timeline[ope_date].append({'amount': amount, 'src_acc': src_acc, 'dst_acc': dst_acc, 'wording': ope.get('wording', ''), 'tags': ope.get('tags', '')})

    # Step B: Scan structural instances of recurring Favorites elements (<fav>)
    for fav in root.findall('fav'):
        raw_next_date = fav.get('nextdate')
        if not raw_next_date: continue
        
        # Tag filter check
        if not _matches_tags(fav.get('tags', ''), filter_tags):
            continue
            
        current_due_date = parse_hb_date(raw_next_date)
        amount = float(fav.get('amount', 0))
        src_acc = fav.get('account')
        dst_acc = fav.get('dst_account')
        wording = fav.get('wording', '').strip().replace('\n', ' ')
        
        every = int(fav.get('every', 1))
        unit = int(fav.get('unit', 0))
        weekend_rule = int(fav.get('weekend', 0))

        if src_acc not in tracked_ids and dst_acc not in tracked_ids:
            continue

        limit = int(fav.get('limit', 0))      # 0 = unlimited
        number = int(fav.get('number', 0))    # how many times already paid (if present)
        remaining = (limit - number) if limit > 0 else None
        occurrence_count = 0
        
        while current_due_date <= end_date:
            if remaining is not None and occurrence_count >= remaining:
                break
            
            final_date = current_due_date
            if final_date.weekday() >= 5:
                if weekend_rule == 1:
                    final_date -= timedelta(days=1 if final_date.weekday() == 5 else 2)
                elif weekend_rule == 2:
                    final_date += timedelta(days=2 if final_date.weekday() == 5 else 1)

            # Route calculation into correct history or future time bins
            if final_date <= end_date:
                if src_acc in tracked_ids and final_date > account_as_of[src_acc]:
                    if final_date < start_date: historical_delta[src_acc] += amount
                    else: timeline[final_date].append({'amount': amount, 'src_acc': src_acc, 'dst_acc': dst_acc, 'wording': wording, 'is_fav': True, 'tags': fav.get('tags', '')})
                if dst_acc in tracked_ids and final_date > account_as_of[dst_acc]:
                    if final_date < start_date: historical_delta[dst_acc] -= amount
                    else: timeline[final_date].append({'amount': amount, 'src_acc': src_acc, 'dst_acc': dst_acc, 'wording': wording, 'is_fav': True, 'tags': fav.get('tags', '')})

            occurrence_count += 1   # count this scheduled occurrence
            
            # Advance recurrence sequence context parameters
            if unit == 0: current_due_date += timedelta(days=every)
            elif unit == 1: current_due_date += timedelta(weeks=every)
            elif unit == 2:
                new_month = current_due_date.month - 1 + every
                new_year = current_due_date.year + (new_month // 12)
                new_month = (new_month % 12) + 1
                try: current_due_date = current_due_date.replace(year=new_year, month=new_month)
                except ValueError:
                    next_month_start = date(new_year, new_month, 1) + timedelta(days=32)
                    current_due_date = date(next_month_start.year, next_month_start.month, 1) - timedelta(days=1)
            elif unit == 3: current_due_date = current_due_date.replace(year=current_due_date.year + every)

    # Step C: Aggregate intermediate historical changes into baseline initial values
    for acc_id in tracked_ids:
        balances[acc_id] += historical_delta[acc_id]

    # Step D: Chronological Execution Core Simulation Ledger Loop
    print("="*110)
    print(f"FORECAST TIMELINE ({start_date.isoformat()} to {end_date.isoformat()})")
    print("="*110)
    print(f"{'Date':<11} | {'Account':<30} | {'Change':<12} | {'Proj Balance':<14} | {'Description / Tags'}")
    print("="*110)

    daily_snapshot_records = {}
    current_step_date = start_date
    
    # Pre-seed initial day snapshot arrays balance state markers
    daily_snapshot_records[current_step_date - timedelta(days=1)] = balances.copy()

    while current_step_date <= end_date:
        if current_step_date in timeline:
            # Deduplicate entries to avoid printing identical double ledger rows for transfers
            seen_txs = set()
            for tx in timeline[current_step_date]:
                tx_key = (tx['amount'], tx['src_acc'], tx['dst_acc'], tx['wording'])
                if tx_key in seen_txs: continue
                seen_txs.add(tx_key)

                src_id, dst_id, amount = tx['src_acc'], tx['dst_acc'], tx['amount']
                desc = tx['wording'][:40]
                tags_display = tx.get('tags', '').strip()
                tag_suffix = f" [tags: {tags_display}]" if tags_display else ""
                
                if dst_id: # Double entry calculation mapping rules
                    if src_id in tracked_ids:
                        balances[src_id] += amount
                        print(f"{current_step_date.isoformat()} | {account_names[src_id]:<30} | {amount:<12,.2f} | ${balances[src_id]:<13,.2f} | TRSF OUT: {desc}{tag_suffix}")
                    if dst_id in tracked_ids:
                        balances[dst_id] -= amount
                        print(f"{current_step_date.isoformat()} | {account_names[dst_id]:<30} | {-amount:<12,.2f} | ${balances[dst_id]:<13,.2f} | TRSF IN: {desc}{tag_suffix}")
                else:
                    if src_id in tracked_ids:
                        balances[src_id] += amount
                        print(f"{current_step_date.isoformat()} | {account_names[src_id]:<30} | {amount:<12,.2f} | ${balances[src_id]:<13,.2f} | {desc}{tag_suffix}")
            print("-" * 110)
            
        daily_snapshot_records[current_step_date] = balances.copy()
        current_step_date += timedelta(days=1)

    # Step E: Trigger structural graphical plot renderer engine parameters mapping states
    generate_graph(daily_snapshot_records, account_names, show_month_end, timeline_data=timeline)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Extracts scheduled operations from native HomeBank (.xhb) XML archives to calculate cash flow projections.",
        epilog="Example: ./forecast.py my_finances.xhb --filter 'PNC' -s 2026-11-01 -e 2027-01-30"
    )
    parser.add_argument("-f", "--filter", action="append", metavar="PATTERN", help="Regex pattern to filter target account names (repeatable: -f Chase -f PNC)")
    parser.add_argument("--tags", action="append", metavar="TAG", help="Only include transactions that have at least one of these tags (repeatable). Example: --tags fixed --tags reserve")
    parser.add_argument("-r", "--reconfigure", action="store_true", help="Bypasses configuration caches forcing onboarding setup wizard prompts")
    parser.add_argument("-s", "--start-date", help="Simulation timeline sequence start date boundary (YYYY-MM-DD)")
    parser.add_argument("-e", "--end-date", help="Simulation timeline sequence absolute end date boundary (YYYY-MM-DD)")
    parser.add_argument("-d", "--days", type=int, help="Relative duration rolling horizon cutoff span parameter (Days)")
    parser.add_argument("-m", "--month-end", action="store_true", help="Aggregates visual performance plots to trace only trailing month end boundaries")
    parser.add_argument("xml_file", help="System path string targeting the native HomeBank transaction file container (.xhb)")
    
    args = parser.parse_args()
    run_forecast(args.xml_file, args.filter, args.reconfigure, args.start_date, args.end_date, args.days, args.month_end, args.tags)
