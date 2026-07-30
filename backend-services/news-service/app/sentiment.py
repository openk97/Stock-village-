import re
from typing import Dict, Any

class IndofinancialSentiment:
    """
    IndoFinancialSentiment: Mesin analisis sentimen berbasis leksikon (kamus kata)
    yang dirancang dan dioptimalkan khusus untuk istilah keuangan, saham, dan makroekonomi
    dalam Bahasa Indonesia. Menghasilkan skor dari -1.0 (sangat negatif/bearish) hingga +1.0 (sangat positif/bullish).
    """
    def __init__(self):
        # Kamus kata positif keuangan Indonesia (Bullish Catalyst)
        self.positive_lexicon = {
            "laba", "untung", "naik", "lonjak", "ekspansi", "menguat", "rekor", "melesat", "terbang",
            "tumbuh", "surplus", "akuisisi", "dividen", "investasi", "optimis", "bullish", "hijau",
            "menggeliat", "meningkat", "keuntungan", "positif", "kinerja_bagus", "akselerasi",
            "overweight", "buy", "beli", "akumulasi", "moncer", "cerah", "menarik", "melaju",
            "stimulus", "pelonggaran", "suku_bunga_turun", "sentimen_positif", "lancar", "efisien"
        }

        # Kamus kata negatif keuangan Indonesia (Bearish Catalyst)
        self.negative_lexicon = {
            "rugi", "turun", "anjlok", "lemah", "tertekan", "ambruk", "deflasi", "inflasi", "koreksi",
            "ambles", "merah", "sentimen_negatif", "pesimis", "bearish", "defisit", "phk", "bangkrut",
            "pailit", "denda", "sanksi", "gugatan", "pangkas", "susut", "melambat", "underweight",
            "sell", "jual", "distribusi", "panik", "ketidakpastian", "krisis", "resesi", "utang_menumpuk",
            "macet", "gagal_bayar", "suku_bunga_naik", "konflik", "perang", "blokir", "suspend", "delisting"
        }

        # Kata penguat (amplifiers) yang melipatgandakan skor sentimen
        self.amplifiers = {"sangat", "luar_biasa", "drastis", "tajam", "signifikan", "pesat", "tinggi"}

        # Kata negasi yang membalikkan arah sentimen (e.g., "tidak untung" -> negatif)
        self.negations = {"tidak", "bukan", "belum", "kurang", "tanpa", "gagal"}

    def analyze_headline(self, text: str) -> Dict[str, Any]:
        """
        Menganalisis teks judul berita dan mengembalikan skor sentimen beserta labelnya.
        """
        # Pembersihan teks dasar
        cleaned_text = text.lower()
        cleaned_text = re.sub(r'[^\w\s]', ' ', cleaned_text)
        words = cleaned_text.split()

        score = 0.0
        matched_positives = []
        matched_negatives = []
        
        # Gabungkan frasa dua kata penting (bigrams) untuk meningkatkan akurasi analisis
        # e.g., "suku bunga turun" -> "suku_bunga_turun"
        text_collapsed = cleaned_text.replace("suku bunga naik", "suku_bunga_naik")
        text_collapsed = text_collapsed.replace("suku bunga turun", "suku_bunga_turun")
        text_collapsed = text_collapsed.replace("gagal bayar", "gagal_bayar")
        text_collapsed = text_collapsed.replace("kinerja bagus", "kinerja_bagus")
        text_collapsed = text_collapsed.replace("sentimen positif", "sentimen_positif")
        text_collapsed = text_collapsed.replace("sentimen negatif", "sentimen_negatif")
        text_collapsed = text_collapsed.replace("luar biasa", "luar_biasa")
        words = text_collapsed.split()

        for idx, word in enumerate(words):
            multiplier = 1.0
            negated = False

            # Cek kata sebelumnya untuk mendeteksi negasi atau penguatan
            if idx > 0:
                prev_word = words[idx - 1]
                if prev_word in self.negations:
                    negated = True
                if prev_word in self.amplifiers:
                    multiplier = 1.5

            if idx > 1:
                prev_prev_word = words[idx - 2]
                if prev_prev_word in self.negations:
                    negated = True

            # Cek kecocokan leksikon
            if word in self.positive_lexicon:
                val = 1.0 * multiplier
                if negated:
                    score -= val  # "tidak untung" menjadi bernilai negatif
                    matched_negatives.append(f"tidak {word}")
                else:
                    score += val
                    matched_positives.append(word)

            elif word in self.negative_lexicon:
                val = 1.0 * multiplier
                if negated:
                    score += val  # "tidak rugi" menjadi bernilai positif
                    matched_positives.append(f"tidak {word}")
                else:
                    score -= val
                    matched_negatives.append(word)

        # Normalisasi skor akhir ke dalam rentang [-1.0, 1.0]
        total_matches = len(matched_positives) + len(matched_negatives)
        if total_matches > 0:
            normalized_score = score / total_matches
        else:
            normalized_score = 0.0

        # Menentukan label sentimen berdasarkan skor normalisasi
        if normalized_score >= 0.15:
            label = "Positive"
        elif normalized_score <= -0.15:
            label = "Negative"
        else:
            label = "Neutral"

        return {
            "headline": text,
            "sentiment": label,
            "score": round(normalized_score, 2),
            "matched_positives": matched_positives,
            "matched_negatives": matched_negatives
        }

if __name__ == "__main__":
    analyzer = IndofinancialSentiment()
    # Test cases
    tests = [
        "Laba bersih BBCA naik sangat tajam kuartal ini",
        "Suku bunga naik membuat pasar properti tertekan rugi besar",
        "IHSG ditutup stagnan hari ini tanpa ada pergerakan berarti",
        "Perusahaan tidak mengalami rugi pada kuartal II"
    ]
    for t in tests:
        print(analyzer.analyze_headline(t))
