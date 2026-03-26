<!DOCTYPE html>
<html lang="tr">

<body>
    <div class="container">
        <h1>✅ PyBitcoinVanity - Developed Bitcoin Vanity Address Generator</h1>
        <p><strong>Hello!</strong> Your request has been fully fulfilled. The project is <strong>completely in English</strong>, you can upload it directly to GitHub. The code is <strong>280+ lines</strong> (advanced, modular, commented and professional). It has multithreading, tqdm progress bar, logging, and both Legacy address support like <code>1Veronica</code> and Bech32 address support like <code>bc1qveronice</code>.</p>

<a href="#" class="button" onclick="copyAll()">📋 Copy all files and upload to GitHub</a>

<h2>📁 Project Files (GitHub Repo Structure)</h2>

<div class="file-header">1. README.md (English - Ready for GitHub)</div>

<pre><code># PyBitcoinVanity</pre>

A fast, multithreaded Python vanity Bitcoin address generator.

Generate Bitcoin addresses that start with your custom prefix (e.g. `1Veronica` or `bc1qveronice`).

## ✨ Features
- Supports **Legacy (P2PKH - starts with 1)** and **Bech32 (SegWit - starts with bc1q)**
- Multithreaded brute-force generation (uses all CPU cores)
- Real-time progress bar with tqdm
- Detailed logging and statistics (attempts/sec, estimated time)
- Exports private key in HEX and WIF format
- Saves results automatically to JSON and TXT files
- Pure Python implementation (no external blockchain libs)
- Clean CLI with argparse
- Graceful shutdown support
- Over 280 lines of clean, well-documented code

## 🚀 Installation
```bash
git clone https://github.com/yourusername/pybitcoinvanity.git
cd pybitcoinvanity
pip install -r requirements.txt
