import sys, os
# Pastikan package app/ dapat di-import saat pytest dijalankan dari folder service
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
