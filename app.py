import os
import numpy as np
import firebase_admin
from firebase_admin import credentials, db
from flask import Flask, jsonify, request
import time
import threading

app = Flask(__name__)


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
    if a <= 20:
        return 1
    elif 20 < a <= 24:
        return (24 - a) / (24 - 20)
    else:
        return 0

def suhu_sejuk(a):
    if a <= 20 or a > 27:
        return 0
    elif 20 < a <= 24:
        return (a - 20) / (24 - 20)
    elif 23.6 < a <= 27:
        return (27 - a) / (27 - 24)
    elif a == 24:
        return 1
    else:
        return 0

def suhu_normal(a):
    if a <= 24 or a > 31:
        return 0
    elif 24 < a <= 27:
        return (a - 24) / (27 - 24)
    elif 27 < a <= 31:
        return (31 - a) / (31 - 27)
    elif a == 27:
        return 1
    else:
        return 0

def suhu_hangat(a):
    if a <= 27 or a > 36:
        return 0
    elif 27 < a <= 31:
        return (a - 27) / (31 - 27)
    elif 31 < a <= 36:
        return (36 - a) / (36 - 31)
    elif a == 31:
        return 1
    else:
        return 0

def suhu_panas(a):
    if a <= 31:
        return 0
    elif 31 < a <= 36:
        return (a - 31) / (36 - 31)
    else: 
        return 1

# Membership untuk Kelembaban Udara 
def kelembaban_udara_kering(b):
    if b <= 40:
        return 1
    elif 40 < b <= 50:
        return (50 - b) / (50 - 40)
    else:
        return 0

def kelembaban_udara_normal(b):
    if b <= 40 or b > 80:
        return 0
    elif 40 < b <= 60:
        return (b - 40) / (60 - 40)
    elif 60 < b <= 80:
        return (80 - b) / (80 - 60)
    elif b == 60:
        return 1
    else:
        return 0

def kelembaban_udara_basah(b):
    if b <= 70:
        return 0
    elif 70 < b <= 80:
        return (b - 70) / (80 - 70)
    else:
        return 1
    
# Membership untuk Kelembaban Tanah
def kelembaban_tanah_kering(c):
    if c <= 70:
        return 1
    elif 70 < c <= 80:
        return (80 - c) / (80 - 70)
    else:
        return 0

def kelembaban_tanah_normal(c):
    if c <= 70 or c > 95:
        return 0
    elif 70 < c <= 85:
        return (c - 70) / (85 - 70)
    elif 85 < c <= 95:
        return (95 - c) / (95 - 85)
    elif c == 85:
        return 1
    else:
        return 0

def kelembaban_tanah_basah(c):
    if c <= 90:
        return 0
    elif 90 < c <= 95:
        return (c - 90) / (95 - 90)
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
        'Kering': kelembaban_udara_kering(kelembaban_udara),
        'Normal': kelembaban_udara_normal(kelembaban_udara),
        'Basah': kelembaban_udara_basah(kelembaban_udara)
    }
    fuzzy_kelembaban_tanah = {
        'Kering': kelembaban_tanah_kering(kelembaban_tanah),
        'Normal': kelembaban_tanah_normal(kelembaban_tanah),
        'Basah': kelembaban_tanah_basah(kelembaban_tanah)
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

    # Mengembalikan nilai fuzzy sebagai bagian dari hasil
    return results, fuzzy_suhu, fuzzy_kelembaban_udara, fuzzy_kelembaban_tanah

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


# Fungsi untuk menentukan kategori output berdasarkan durasi
def get_output_category(durasi):
    # Cek rentang nilai untuk setiap kategori
    if 0 <= durasi <= 7.5:
        return "Mati"
    elif durasi <= 15:
        return "Cepat"
    elif durasi <= 22.5:
        return "Sebentar"
    elif durasi <= 30:
        return "Agak Sebentar"
    elif durasi <= 37.5:
        return "Sedang"
    elif durasi <= 45:
        return "Agak Lumayan"
    elif durasi <= 52.5:
        return "Lumayan"
    elif durasi <= 60:
        return "Lama"
    else:
        return "Sangat Lama"

# Variabel untuk melacak status pompa
pump_running = False
last_processed_time = 0

# Fungsi untuk memproses data sensor secara otomatis
def process_sensor_data_automatic():
    global pump_running, last_processed_time
    
    try:
        # Mengambil data terbaru dari Firebase
        sensor_ref = db.reference('MonitoringData')
        pump_ref = db.reference('pump_control')
        fuzzy_values_ref = db.reference('FuzzyValues')  # Referensi baru untuk nilai fuzzy
        
        # Stream listener untuk mendeteksi perubahan data sensor
        def sensor_listener(event):
            global pump_running, last_processed_time
            current_time = int(time.time())
            
            # Hindari pemrosesan berulang dalam waktu singkat (minimal 10 detik interval)
            if current_time - last_processed_time < 10:
                return
                
            last_processed_time = current_time
            
            if pump_running:
                print("Pompa sedang berjalan, menunggu selesai...")
                return
                
            print("Mendeteksi perubahan data sensor, memproses...")
            
            # Ambil data sensor terbaru
            sensor_data = sensor_ref.get()
            if not sensor_data:
                print("Tidak ada data sensor di Firebase")
                return
                
            # Menghitung hasil fuzzy
            suhu = sensor_data.get("Suhu_Terkalibrasi", 0)
            kelembaban_udara = sensor_data.get("Kelembaban_Udara_Terkalibrasi", 0)
            kelembaban_tanah = sensor_data.get("Kelembaban_Tanah_Terkalibrasi", 0)
            
            # Evaluasi fuzzy rules
            results, fuzzy_suhu, fuzzy_kelembaban_udara, fuzzy_kelembaban_tanah = evaluate_rules(
                suhu, kelembaban_udara, kelembaban_tanah
            )
            
            # Simpan nilai fuzzy ke Firebase
            fuzzy_values = {
                'Suhu': {k: round(v, 4) for k, v in fuzzy_suhu.items()},
                'KelembapanUdara': {k: round(v, 4) for k, v in fuzzy_kelembaban_udara.items()},
                'KelembapanTanah': {k: round(v, 4) for k, v in fuzzy_kelembaban_tanah.items()},
                'timestamp': current_time
            }
            fuzzy_values_ref.set(fuzzy_values)
            
            # Simpan nilai rule yang diaktifkan (dengan derajat > 0)
            activated_rules = []
            for degree, output_label in results:
                if degree > 0:
                    activated_rules.append({
                        'derajat': round(degree, 4),
                        'output': output_label
                    })
            
            if activated_rules:
                fuzzy_values_ref.child('AktifasiRule').set(activated_rules)
            
            output_durasi = defuzzify(results)
            output_kategori = get_output_category(output_durasi)
            
            # Menyimpan hasil ke Firebase untuk diambil oleh ESP8266
            result_data = {}
            
            # Cek apakah kategori output adalah "Mati"
            if output_kategori == "Mati":
                print(f"Output dalam kategori 'Mati' ({output_durasi} detik), pompa tidak akan dijalankan")
                # Set durasi ke 0 untuk kategori "Mati" agar ESP tidak menjalankan pompa
                result_data = {
                    'durasi': 0,  # Set durasi ke 0
                    'durasi_asli': round(output_durasi, 2),  # Simpan durasi asli untuk referensi
                    'kategori': output_kategori,
                    'timestamp': current_time,
                    'processed': True,
                    'pump_should_run': False  # Flag untuk ESP8266
                }
                # Update status pompa ke "finished" agar tidak menunggu pompa berjalan
                db.reference('pump_status').set({'status': 'finished', 'timestamp': current_time})
            else:
                # Untuk kategori selain "Mati", kirim durasi normal
                result_data = {
                    'durasi': round(output_durasi, 2),
                    'kategori': output_kategori,
                    'timestamp': current_time,
                    'processed': True,
                    'pump_should_run': True  # Flag untuk ESP8266
                }
                pump_running = True
                print(f"Pompa akan berjalan selama {output_durasi} detik (kategori: {output_kategori})")
                
                # Set timer untuk menandai selesainya penyiraman
                def pump_finished():
                    global pump_running
                    pump_running = False
                    print("Pompa selesai, siap untuk pemrosesan data sensor berikutnya")
                
                # Timer untuk mendeteksi kapan pompa selesai
                timer = threading.Timer(output_durasi + 5, pump_finished)
                timer.daemon = True
                timer.start()
            
            # Simpan hasil ke Firebase
            pump_ref.set(result_data)
        
        # Fungsi untuk mendeteksi status pompa
        def pump_status_listener(event):
            global pump_running
            
            if event.data and 'status' in event.data:
                if event.data['status'] == 'finished':
                    pump_running = False
                    print("Status pompa: selesai (berdasarkan feedback ESP8266)")
                elif event.data['status'] == 'running':
                    pump_running = True
                    print("Status pompa: berjalan (berdasarkan feedback ESP8266)")
        
        # Daftarkan listener untuk data sensor dan status pompa
        sensor_ref.listen(sensor_listener)
        db.reference('pump_status').listen(pump_status_listener)
        
        print("Background monitor started - menunggu perubahan data sensor...")
        
    except Exception as e:
        print(f"Error in background process: {str(e)}")
        time.sleep(10)  # Tunggu 10 detik sebelum mencoba lagi
        process_sensor_data_automatic()

# Jalankan proses background di thread terpisah
background_thread = threading.Thread(target=process_sensor_data_automatic)
background_thread.daemon = True
background_thread.start()

# Route tetap ada untuk backward compatibility
@app.route('/process_sensor_data', methods=['GET'])
def process_sensor_data():
    try:
        # Mengambil data terbaru dari Firebase
        sensor_ref = db.reference('MonitoringData')
        sensor_data = sensor_ref.get()
        
        if not sensor_data:
            return jsonify({'error': 'No sensor data found in Firebase'}), 404
        
        # Menghitung hasil fuzzy
        suhu = sensor_data.get("Suhu_Terkalibrasi", 0)
        kelembaban_udara = sensor_data.get("Kelembaban_Udara_Terkalibrasi", 0)
        kelembaban_tanah = sensor_data.get("Kelembaban_Tanah_Terkalibrasi", 0)
        
        # Evaluasi fuzzy rules dengan mendapatkan nilai fuzzy
        results, fuzzy_suhu, fuzzy_kelembaban_udara, fuzzy_kelembaban_tanah = evaluate_rules(
            suhu, kelembaban_udara, kelembaban_tanah
        )
        
        # Simpan nilai fuzzy ke Firebase
        fuzzy_values_ref = db.reference('FuzzyValues')
        current_time = int(time.time())
        
        fuzzy_values = {
            'Suhu': {k: round(v, 4) for k, v in fuzzy_suhu.items()},
            'KelembapanUdara': {k: round(v, 4) for k, v in fuzzy_kelembaban_udara.items()},
            'KelembapanTanah': {k: round(v, 4) for k, v in fuzzy_kelembaban_tanah.items()},
            'timestamp': current_time
        }
        fuzzy_values_ref.set(fuzzy_values)
        
        # Simpan nilai rule yang diaktifkan (dengan derajat > 0)
        activated_rules = []
        for degree, output_label in results:
            if degree > 0:
                activated_rules.append({
                    'derajat': round(degree, 4),
                    'output': output_label
                })
        
        if activated_rules:
            fuzzy_values_ref.child('AktifasiRule').set(activated_rules)
        
        output_durasi = defuzzify(results)
        output_kategori = get_output_category(output_durasi)
        
        # Menyimpan hasil ke Firebase untuk diambil oleh ESP8266
        result_ref = db.reference('pump_control')
        
        # Cek apakah kategori output adalah "Mati"
        if output_kategori == "Mati":
            result_data = {
                'durasi': 0,  # Set durasi ke 0
                'durasi_asli': round(output_durasi, 2),  # Simpan durasi asli untuk referensi
                'kategori': output_kategori,
                'timestamp': current_time,
                'processed': True,
                'pump_should_run': False  # Flag untuk ESP8266
            }
            # Update status pompa ke finished
            db.reference('pump_status').set({
                'status': 'finished', 
                'timestamp': current_time
            })
        else:
            result_data = {
                'durasi': round(output_durasi, 2),
                'kategori': output_kategori,
                'timestamp': current_time,
                'processed': True,
                'pump_should_run': True  # Flag untuk ESP8266
            }
        
        # Simpan hasil ke Firebase
        result_ref.set(result_data)
        
        return jsonify({
            'success': True,
            'input': {
                'suhu': suhu,
                'kelembaban_udara': kelembaban_udara,
                'kelembaban_tanah': kelembaban_tanah
            },
            'fuzzy_values': fuzzy_values,
            'output': result_data
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/status', methods=['GET'])
def status():
    return jsonify({
        'status': 'online',
        'running_in_background': True,
        'timestamp': int(time.time())
    })

# Menjalankan aplikasi
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)