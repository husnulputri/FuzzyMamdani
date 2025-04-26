import os
import numpy as np
import firebase_admin
from firebase_admin import credentials, db
from flask import Flask, jsonify, request
import time

app = Flask(__name__)

# Initialize Firebase
# Di Railway, Anda perlu set FIREBASE_CREDENTIALS sebagai environment variable
# yang berisi konten JSON dari service account key
if 'FIREBASE_CREDENTIALS' in os.environ:
    cred_dict = eval(os.environ.get('FIREBASE_CREDENTIALS'))
    cred = credentials.Certificate(cred_dict)
else:
    # Untuk pengembangan lokal, gunakan file json
    cred = credentials.Certificate('path/to/serviceAccountKey.json')

firebase_admin.initialize_app(cred, {
    'databaseURL': os.environ.get('FIREBASE_DATABASE_URL', 'https://project-penyiraman-pencahayaan-default-rtdb.asia-southeast1.firebasedatabase.app/')
})

# Fungsi Membership untuk Suhu
def suhu_dingin(a):
    if a <= 15:
        return 1
    elif 15 < a <= 20:
        return (20 - a) / (20 - 15)
    else:
        return 0

def suhu_sejuk(a):
    if a <= 15 or a > 25:
        return 0
    elif 15 < a <= 20:
        return (a - 15) / (20 - 15)
    elif 20 < a <= 25:
        return (25 - a) / (25 - 20)
    elif a == 20:
        return 1
    else:
        return 0

def suhu_normal(a):
    if a <= 20 or a > 30:
        return 0
    elif 20 < a <= 25:
        return (a - 20) / (25 - 20)
    elif 25 < a <= 30:
        return (30 - a) / (30 - 25)
    elif a == 25:
        return 1
    else:
        return 0

def suhu_hangat(a):
    if a <= 25 or a > 35:
        return 0
    elif 25 < a <= 30:
        return (a - 25) / (30 - 25)
    elif 30 < a <= 35:
        return (35 - a) / (35 - 30)
    elif a == 30:
        return 1
    else:
        return 0

def suhu_panas(a):
    if a <= 30:
        return 0
    elif 30 < a <= 35:
        return (a - 30) / (35 - 30)
    else:  # a > 35
        return 1

# Membership untuk Kelembaban Udara dan Kelembaban Tanah
def kelembaban_kering(x):
    if x <= 25:
        return 1
    elif 25 < x <= 36:
        return (36 - x) / (36 - 25)
    else:
        return 0

def kelembaban_normal(x):
    if x <= 25 or x > 75:
        return 0
    elif 25 < x <= 50:
        return (x - 25) / (50 - 25)
    elif 50 < x <= 75:
        return (75 - x) / (75 - 50)
    elif x == 50:
        return 1
    else:
        return 0

def kelembaban_basah(x):
    if x <= 64:
        return 0
    elif 64 < x <= 75:
        return (x - 64) / (75 - 64)
    else:
        return 1

# Output mapping (durasi dalam detik)
output_values = {
    'Mati': (0, 7.5),
    'Cepat': (0, 15),
    'Sebentar': (7.5, 22.5),
    'Agak Sebentar': (15, 30),
    'Sedang': (22.5, 37.5),
    'Agak Lumayan': (30, 45),
    'Lumayan': (37.5, 52.5),
    'Lama': (45, 60),
    'Sangat Lama': (52.5, 60),
}

# Fuzzy Rules
rules = [
    # Format: (suhu, udara, tanah, output)
    ('Panas', 'Kering', 'Kering', 'Sangat Lama'),
    ('Hangat', 'Kering', 'Kering', 'Sangat Lama'),
    ('Normal', 'Kering', 'Kering', 'Sangat Lama'),
    ('Sejuk', 'Kering', 'Kering', 'Sangat Lama'),
    ('Dingin', 'Kering', 'Kering', 'Sangat Lama'),
    ('Panas', 'Normal', 'Kering', 'Lama'),
    ('Hangat', 'Normal', 'Kering', 'Lama'),
    ('Normal', 'Normal', 'Kering', 'Lama'),
    ('Sejuk', 'Normal', 'Kering', 'Lama'),
    ('Dingin', 'Normal', 'Kering', 'Lama'),
    ('Panas', 'Basah', 'Kering', 'Lumayan'), 
    ('Hangat', 'Basah', 'Kering', 'Lumayan'), 
    ('Normal', 'Basah', 'Kering', 'Lumayan'), 
    ('Sejuk', 'Basah', 'Kering', 'Lumayan'), 
    ('Dingin', 'Basah', 'Kering', 'Lumayan'),
    ('Panas', 'Kering', 'Normal', 'Agak Lumayan'), 
    ('Hangat', 'Kering', 'Normal', 'Agak Lumayan'), 
    ('Normal', 'Kering', 'Normal', 'Agak Lumayan'), 
    ('Sejuk', 'Kering', 'Normal', 'Agak Lumayan'), 
    ('Dingin', 'Kering', 'Normal', 'Agak Lumayan'),
    ('Panas', 'Normal', 'Normal', 'Sedang'), 
    ('Hangat', 'Normal', 'Normal', 'Sedang'), 
    ('Normal', 'Normal', 'Normal', 'Sedang'), 
    ('Sejuk', 'Normal', 'Normal', 'Sedang'), 
    ('Dingin', 'Normal', 'Normal', 'Sedang'), 
    ('Panas', 'Basah', 'Normal', 'Agak Sebentar'), 
    ('Hangat', 'Basah', 'Normal', 'Agak Sebentar'), 
    ('Normal', 'Basah', 'Normal', 'Agak Sebentar'), 
    ('Sejuk', 'Basah', 'Normal', 'Agak Sebentar'), 
    ('Dingin', 'Basah', 'Normal', 'Agak Sebentar'), 
    ('Panas', 'Kering', 'Basah', 'Sebentar'), 
    ('Hangat', 'Kering', 'Basah', 'Sebentar'), 
    ('Normal', 'Kering', 'Basah', 'Sebentar'), 
    ('Sejuk', 'Kering', 'Basah', 'Sebentar'), 
    ('Dingin', 'Kering', 'Basah', 'Sebentar'), 
    ('Panas', 'Normal', 'Basah', 'Cepat'), 
    ('Hangat', 'Normal', 'Basah', 'Cepat'), 
    ('Normal', 'Normal', 'Basah', 'Cepat'), 
    ('Sejuk', 'Normal', 'Basah', 'Cepat'), 
    ('Dingin', 'Normal', 'Basah', 'Cepat'), 
    ('Panas', 'Basah', 'Basah', 'Mati'), 
    ('Hangat', 'Basah', 'Basah', 'Mati'), 
    ('Normal', 'Basah', 'Basah', 'Mati'), 
    ('Sejuk', 'Basah', 'Basah', 'Mati'), 
    ('Dingin', 'Basah', 'Basah', 'Mati'), 
    
]

# Fungsi Evaluasi Rule
def evaluate_rules(suhu, kelembaban_udara, kelembaban_tanah):
    fuzzy_suhu = {
        'Dingin': suhu_dingin(suhu),
        'Sejuk': suhu_sejuk(suhu),
        'Normal': suhu_normal(suhu),
        'Hangat': suhu_hangat(suhu),
        'Panas': suhu_panas(suhu)
    }
    fuzzy_kelembaban_udara = {
        'Kering': kelembaban_kering(kelembaban_udara),
        'Normal': kelembaban_normal(kelembaban_udara),
        'Basah': kelembaban_basah(kelembaban_udara)
    }
    fuzzy_kelembaban_tanah = {
        'Kering': kelembaban_kering(kelembaban_tanah),
        'Normal': kelembaban_normal(kelembaban_tanah),
        'Basah': kelembaban_basah(kelembaban_tanah)
    }

    results = []

    for rule in rules:
        suhu_label, udara_label, tanah_label, output_label = rule
        degree = min(
            fuzzy_suhu[suhu_label],
            fuzzy_kelembaban_udara[udara_label],
            fuzzy_kelembaban_tanah[tanah_label]
        )
        results.append((degree, output_label))

    return results

# Defuzzifikasi (Menggunakan Metode rata-rata terpusat Centroid)
def defuzzify(results):
    numerator = 0
    denominator = 0
    for degree, output_label in results:
        if degree > 0:
            output_range = output_values[output_label]
            output_center = np.mean(output_range)  # ambil titik tengah
            numerator += degree * output_center
            denominator += degree

    if denominator == 0:
        return 0  # Tidak ada aktivasi rule
    else:
        return numerator / denominator

# Route untuk mendapatkan hasil defuzzifikasi berdasarkan data sensor
@app.route('/calculate_fuzzy', methods=['POST'])
def calculate_fuzzy():
    data = request.json
    
    suhu = data.get("Suhu_Terkalibrasi", 0)
    kelembaban_udara = data.get("Kelembaban_Udara_Terkalibrasi", 0)
    kelembaban_tanah = data.get("Kelembaban_Tanah_Terkalibrasi", 0)
    
    results = evaluate_rules(suhu, kelembaban_udara, kelembaban_tanah)
    output_durasi = defuzzify(results)
    
    return jsonify({
        'durasi': round(output_durasi, 2),
        'timestamp': int(time.time())
    })

# Route untuk membaca data sensor dari Firebase dan menghitung fuzzy logic
@app.route('/process_sensor_data', methods=['GET'])
def process_sensor_data():
    try:
        # Mengambil data terbaru dari Firebase
        sensor_ref = db.reference('sensors/latest')
        sensor_data = sensor_ref.get()
        
        if not sensor_data:
            return jsonify({'error': 'No sensor data found in Firebase'}), 404
        
        # Menghitung hasil fuzzy
        suhu = sensor_data.get("Suhu_Terkalibrasi", 0)
        kelembaban_udara = sensor_data.get("Kelembaban_Udara_Terkalibrasi", 0)
        kelembaban_tanah = sensor_data.get("Kelembaban_Tanah_Terkalibrasi", 0)
        
        results = evaluate_rules(suhu, kelembaban_udara, kelembaban_tanah)
        output_durasi = defuzzify(results)
        
        # Menyimpan hasil ke Firebase untuk diambil oleh ESP8266
        result_ref = db.reference('pump_control')
        result_data = {
            'durasi': round(output_durasi, 2),
            'timestamp': int(time.time()),
            'processed': True
        }
        result_ref.set(result_data)
        
        return jsonify({
            'success': True,
            'input': {
                'suhu': suhu,
                'kelembaban_udara': kelembaban_udara,
                'kelembaban_tanah': kelembaban_tanah
            },
            'output': result_data
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Route untuk polling data baru
@app.route('/status', methods=['GET'])
def status():
    return jsonify({
        'status': 'online',
        'timestamp': int(time.time())
    })

# Menjalankan aplikasi
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)