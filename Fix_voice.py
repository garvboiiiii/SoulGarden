@app.route("/fix_voice_paths")
def fix_voice_paths():
    try:
        c.execute("""
            UPDATE memories
            SET voice_path = REPLACE(voice_path, 'static/', '')
            WHERE voice_path LIKE 'static/%'
        """)
        conn.commit()
        return "✅ Voice paths fixed!"
    except Exception as e:
        return f"❌ Error: {e}", 500
