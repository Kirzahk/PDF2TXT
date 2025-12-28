import tkinter as tk
from tkinter import filedialog, ttk, scrolledtext, messagebox
import threading
import os
import glob 
import fitz # PyMuPDF
import argostranslate.package
import argostranslate.translate
import time

# --- CONFIGURACIÓN ESTÁTICA ---
SOURCE_LANG_CODE = "en" 
TARGET_LANGS = {"Español": "es", "Inglés": "en"}
TARGET_LANG_DEFAULT = "es"
CHECKPOINT_PAGES = 50 

# ----------------------------------------------------------------------
## Instalación del Paquete de Idiomas
# ----------------------------------------------------------------------

def instalar_paquete_traduccion(source_code, target_code, callback_progreso):
    """Verifica e instala el paquete de idioma de ArgoTranslate si no está presente."""
    callback_progreso(f"Verificando paquete de traducción {source_code} -> {target_code}...")
    try:
        paquetes_instalados = argostranslate.package.get_installed_packages()
        paquete_requerido_instalado = any(
            p.from_code == source_code and p.to_code == target_code
            for p in paquetes_instalados
        )
        
        if not paquete_requerido_instalado:
            callback_progreso(f"⏳ Instalando paquete '{source_code}' a '{target_code}'. Esto puede tardar...")
            available_packages = argostranslate.package.get_available_packages()
            package_to_install = next(
                filter(
                    lambda x: x.from_code == source_code and x.to_code == target_code,
                    available_packages
                ), 
                None 
            )
            
            if package_to_install:
                downloaded_path = package_to_install.download()
                argostranslate.package.install_from_path(downloaded_path)
                callback_progreso(f"✅ Paquete de traducción instalado con éxito.")
                return True
            else:
                callback_progreso(f"❌ ERROR: No se encontró el paquete de traducción {source_code} -> {target_code}.", error=True)
                return False
        
        callback_progreso("✅ Paquete de traducción ya está instalado y listo.")
        return True
        
    except Exception as e:
        callback_progreso(f"❌ Error al instalar/verificar paquete de traducción: {e}", error=True)
        return False

# ----------------------------------------------------------------------
## Extracción, Traducción y Guardado
# ----------------------------------------------------------------------

def traducir_bloque(text, source_code, target_code, callback_progreso):
    """Traduce un bloque de texto usando ArgoTranslate localmente."""
    try:
        translated_text = argostranslate.translate.translate(text, source_code, target_code)
        return translated_text
    except Exception as e:
        callback_progreso(f"❌ Error durante la traducción de un bloque: {e}", error=True)
        return f"[ERROR DE TRADUCCIÓN: {text[:50]}...]"

def guardar_texto_traducido(ruta_original, texto_traducido, target_name, callback_progreso):
    """Guarda el texto traducido en un archivo .txt con el sufijo _[idioma]."""
    try:
        base_name = os.path.splitext(ruta_original)[0]
        ruta_salida = f"{base_name}_{target_name}.txt"
        with open(ruta_salida, "w", encoding="utf-8") as f:
            f.write(texto_traducido)
        callback_progreso(f"💾 Traducción guardada con éxito en: {os.path.basename(ruta_salida)}")
    except Exception as e:
        callback_progreso(f"❌ Error al guardar el archivo: {e}", error=True)

def guardar_checkpoint(ruta_pdf, texto_acumulado, target_name, num_pagina, callback_progreso):
    """Guarda el texto acumulado hasta la página actual en un archivo de checkpoint."""
    try:
        base_name = os.path.splitext(ruta_pdf)[0]
        ruta_checkpoint = f"{base_name}_{target_name}_CHECKPOINT_{num_pagina}.txt"
        with open(ruta_checkpoint, "w", encoding="utf-8") as f:
            f.write(texto_acumulado)
        callback_progreso(f"💾 CHECKPOINT: Guardado progreso hasta Pág. {num_pagina} en: {os.path.basename(ruta_checkpoint)}")
    except Exception as e:
        callback_progreso(f"❌ Error al guardar el checkpoint: {e}", error=True)

def procesar_pdf_individual(ruta_pdf, target_code, target_name, callback_progreso, callback_paginas):
    """Lee un PDF, extrae el texto por bloques y lo traduce."""
    texto_transcrito = []
    texto_traducido = []
    texto_traducido_acumulado = "" 
    
    try:
        doc = fitz.open(ruta_pdf)
        num_paginas = len(doc)
        
        # Actualizar el contador de páginas en la UI
        callback_paginas(num_paginas)
        
        for i in range(num_paginas):
            pagina_num = i + 1
            pagina = doc[i]
            
            bloques = pagina.get_text("blocks")
            bloques.sort(key=lambda block: (block[1], block[0])) 

            callback_progreso(f"✍️ Procesando Página {pagina_num}/{num_paginas}...")
            
            for block_index, bloque in enumerate(bloques):
                texto_original = bloque[4].strip()
                if texto_original and len(texto_original) > 1: 
                    texto_transcrito.append(texto_original)
                    callback_progreso(f"🔄 Traduciendo bloque {block_index+1} de la página {pagina_num}...")
                    
                    texto_traducido_bloque = traducir_bloque(texto_original, "en", target_code, callback_progreso) 
                    texto_traducido.append(texto_traducido_bloque)
                    texto_traducido_acumulado += texto_traducido_bloque + "\n\n"

            if pagina_num % CHECKPOINT_PAGES == 0 and pagina_num > 0:
                 guardar_checkpoint(ruta_pdf, texto_traducido_acumulado, target_name, pagina_num, callback_progreso)
            
        doc.close()
        return "\n\n".join(texto_transcrito), "\n\n".join(texto_traducido)

    except Exception as e:
        callback_progreso(f"❌ ERROR al procesar '{os.path.basename(ruta_pdf)}': {e}", error=True)
        return None, None


# ======================================================================
## Clase Principal de la Aplicación TKINTER
# ======================================================================

class AppTraductorPDF(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("📄 Traductor Local de PDF Recursivo")
        self.geometry("1000x750")
        
        self.ruta_directorio = tk.StringVar(value="Selecciona un directorio...")
        self.contador_archivos = tk.StringVar(value="Archivos: 0 / 0")
        self.paginas_archivo = tk.StringVar(value="Páginas: 0")
        self.titulo_procesando = tk.StringVar(value="Archivo actual: Ninguno") 
        self.idioma_seleccionado = tk.StringVar(value="Español") 
        
        self._crear_widgets()
        
    def _crear_widgets(self):
        # --- Frame de Configuración Superior ---
        frame_config = ttk.Frame(self, padding="10")
        frame_config.pack(fill='x')
        
        ttk.Label(frame_config, text="Directorio:").pack(side=tk.LEFT, padx=(0, 5))
        ttk.Entry(frame_config, textvariable=self.ruta_directorio, width=55, state='readonly').pack(side=tk.LEFT, padx=(0, 10), expand=True, fill='x')
        ttk.Button(frame_config, text="Seleccionar Directorio", command=self.seleccionar_directorio).pack(side=tk.LEFT)
        
        ttk.Label(frame_config, text="Traducir a:").pack(side=tk.LEFT, padx=(15, 5))
        self.idioma_combobox = ttk.Combobox(frame_config, textvariable=self.idioma_seleccionado, values=list(TARGET_LANGS.keys()), state="readonly", width=10)
        self.idioma_combobox.set("Español")
        self.idioma_combobox.pack(side=tk.LEFT, padx=(0, 20))
        
        self.btn_procesar = ttk.Button(frame_config, text="INICIAR TRADUCCIÓN", command=self.iniciar_proceso_thread, style="Accent.TButton")
        self.btn_procesar.pack(side=tk.RIGHT)

        self.style = ttk.Style(self)
        self.style.configure("Accent.TButton", foreground="white", background="#4CAF50", font=('Arial', 10, 'bold'))
        self.style.map("Accent.TButton", background=[('active', '#388E3C')])

        ttk.Separator(self, orient='horizontal').pack(fill='x', padx=10, pady=5)
        
        # --- Info Bar (Archivo, Páginas y Contador) ---
        frame_titulo_info = ttk.Frame(self, padding="0 0 10 0")
        frame_titulo_info.pack(fill='x', padx=10, pady=(5, 0))
        
        ttk.Label(frame_titulo_info, textvariable=self.titulo_procesando, font=('Arial', 10, 'bold')).pack(side=tk.LEFT, anchor='w')
        ttk.Label(frame_titulo_info, textvariable=self.contador_archivos, font=('Arial', 10, 'bold'), foreground='darkblue').pack(side=tk.RIGHT, anchor='e')
        ttk.Label(frame_titulo_info, textvariable=self.paginas_archivo, font=('Arial', 10, 'bold'), foreground='#E67E22').pack(side=tk.RIGHT, padx=(0, 25))
        
        # --- Área de Log ---
        ttk.Label(self, text="Log de Procesamiento:").pack(padx=10, pady=(10, 0), anchor='w')
        self.log_area = scrolledtext.ScrolledText(self, wrap=tk.WORD, height=10, state='disabled', font=('Consolas', 9))
        self.log_area.pack(padx=10, pady=(0, 5), fill='x')

        # --- Contenedor de Resultados ---
        frame_resultados = ttk.Frame(self, padding="10")
        frame_resultados.pack(fill='both', expand=True)
        self.notebook = ttk.Notebook(frame_resultados)
        self.notebook.pack(fill='both', expand=True)

        frame_transcripcion = ttk.Frame(self.notebook)
        self.texto_transcripcion = scrolledtext.ScrolledText(frame_transcripcion, wrap=tk.WORD, font=('Arial', 10), state=tk.DISABLED)
        self.texto_transcripcion.pack(fill='both', expand=True)
        self.notebook.add(frame_transcripcion, text="  Texto Original  ")

        frame_traduccion = ttk.Frame(self.notebook)
        self.texto_traduccion = scrolledtext.ScrolledText(frame_traduccion, wrap=tk.WORD, font=('Arial', 10), state=tk.DISABLED)
        self.texto_traduccion.pack(fill='both', expand=True)
        self.notebook.add(frame_traduccion, text="  Traducción Destino  ")

    def seleccionar_directorio(self):
        directorio = filedialog.askdirectory(title="Selecciona el Directorio con Archivos PDF")
        if directorio:
            self.ruta_directorio.set(directorio)
            self.actualizar_log(f"📁 Directorio seleccionado: {os.path.basename(directorio)}\n")
            self.limpiar_resultados()
            self.contador_archivos.set("Archivos: 0 / 0")
            self.paginas_archivo.set("Páginas: 0")
            self.titulo_procesando.set("Archivo actual: Ninguno")

    def iniciar_proceso_thread(self):
        ruta = self.ruta_directorio.get()
        if not os.path.isdir(ruta) or ruta == "Selecciona un directorio...":
            messagebox.showerror("Error", "Selecciona un directorio válido.")
            return
            
        self.btn_procesar.config(state=tk.DISABLED, text="TRADUCIENDO...")
        self.limpiar_resultados()
        
        idioma_nombre = self.idioma_seleccionado.get()
        target_code = TARGET_LANGS.get(idioma_nombre, TARGET_LANG_DEFAULT)
        hilo = threading.Thread(target=self.ejecutar_procesamiento, args=(target_code, idioma_nombre))
        hilo.start()

    def ejecutar_procesamiento(self, target_code, target_name):
        try:
            ruta_raiz = self.ruta_directorio.get()
            if not instalar_paquete_traduccion(SOURCE_LANG_CODE, target_code, self.actualizar_log):
                 return 

            archivos_pdf = glob.glob(ruta_raiz + '/**/*.pdf', recursive=True)
            total_archivos = len(archivos_pdf)
            
            if total_archivos == 0:
                self.actualizar_log("⚠️ No se encontraron archivos PDF.", error=True)
                return
            
            archivos_procesados = 0
            for i, ruta_pdf in enumerate(archivos_pdf):
                if not os.path.exists(ruta_pdf): continue
                
                nombre_archivo = os.path.basename(ruta_pdf)
                archivos_procesados += 1
                
                self.after(0, lambda name=nombre_archivo: self.titulo_procesando.set(f"Archivo actual: {name}"))
                self.after(0, lambda proc=archivos_procesados, total=total_archivos: self.contador_archivos.set(f"Archivos: {proc} / {total}"))

                transcripcion, traduccion = procesar_pdf_individual(
                    ruta_pdf, 
                    target_code, 
                    target_name, 
                    self.actualizar_log,
                    lambda p: self.after(0, lambda val=p: self.paginas_archivo.set(f"Páginas: {val}"))
                )
                
                if transcripcion and traduccion:
                    guardar_texto_traducido(ruta_pdf, traduccion, target_name, self.actualizar_log)
                    self.after(0, lambda t=transcripcion, d=traduccion: self._mostrar_resultados_ui(t, d))

            self.actualizar_log("✨ Proceso COMPLETADO.")
        except Exception as e:
            self.actualizar_log(f"❌ ERROR: {e}", error=True)
        finally:
            self.after(0, lambda: self.btn_procesar.config(state=tk.NORMAL, text="INICIAR TRADUCCIÓN"))

    def _mostrar_resultados_ui(self, transcripcion, traduccion):
        self.texto_transcripcion.config(state=tk.NORMAL)
        self.texto_transcripcion.delete('1.0', tk.END)
        self.texto_transcripcion.insert('1.0', transcripcion)
        self.texto_transcripcion.config(state=tk.DISABLED)
        
        self.texto_traduccion.config(state=tk.NORMAL)
        self.texto_traduccion.delete('1.0', tk.END)
        self.texto_traduccion.insert('1.0', traduccion)
        self.texto_traduccion.config(state=tk.DISABLED)
        self.notebook.select(1)

    def limpiar_resultados(self):
        for widget in [self.texto_transcripcion, self.texto_traduccion]:
            widget.config(state=tk.NORMAL)
            widget.delete('1.0', tk.END)
            widget.config(state=tk.DISABLED)

    def actualizar_log(self, mensaje, error=False, clear=False):
        self.after(0, lambda: self._actualizar_log_ui(mensaje, error, clear))

    def _actualizar_log_ui(self, mensaje, error, clear):
        self.log_area.config(state=tk.NORMAL)
        if clear: self.log_area.delete('1.0', tk.END)
        color = "red" if error else "green" if any(x in mensaje for x in ["✅", "✨", "💾"]) else "black"
        self.log_area.insert(tk.END, f"[{time.strftime('%H:%M:%S')}] {mensaje}\n", color)
        self.log_area.tag_config(color, foreground=color)
        self.log_area.see(tk.END)
        self.log_area.config(state=tk.DISABLED)

if __name__ == "__main__":
    app = AppTraductorPDF()
    app.mainloop()