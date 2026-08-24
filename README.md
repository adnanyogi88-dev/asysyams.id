# Asy-Syams Islamic School

Pemulihan website `asysyams.id` berdasarkan arsip Internet Archive sampai
11 Juni 2026.

Repositori ini mempertahankan struktur permalink WordPress, halaman sekolah,
artikel, kategori, tag, gambar, stylesheet, JavaScript, dan metadata SEO yang
masih tersedia pada Wayback Machine. Hasilnya berupa website statis yang dapat
langsung dipublikasikan melalui GitHub Pages, Cloudflare Pages, atau Vercel.

## Memperbarui hasil pemulihan

```bash
python3 scripts/restore_wayback.py --snapshot 20260611235959 --workers 14
```

Proses otomatis juga tersedia melalui GitHub Actions pada workflow
**Restore archived Asy-Syams website**.

## Struktur hasil

- `index.html`: halaman utama berdasarkan snapshot 11 Juni 2026.
- `<slug>/index.html`: halaman sekolah dan artikel dengan URL asli.
- `category/`, `tag/`, `author/`, dan `page/`: arsip navigasi WordPress.
- `wp-content/` dan `wp-includes/`: aset tampilan yang berhasil dipulihkan.
- `content/articles/`: salinan artikel dalam format Markdown.
- `content/articles.json`: indeks metadata seluruh artikel yang dipulihkan.
- `_archive/manifest.json`: sumber snapshot dan status pemulihan tiap URL.
- `sitemap.xml` dan `robots.txt`: konfigurasi SEO untuk situs statis.
