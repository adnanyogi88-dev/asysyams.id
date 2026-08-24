(function () {
  "use strict";

  var referenceProfiles = {
    educationBusiness: {
      heading: "Perspektif usaha terkait",
      introduction: "Saat membandingkan model bisnis pendidikan, pelaku usaha juga dapat mempelajari pola kemitraan pada sektor kebutuhan harian melalui ",
      firstLink: {
        href: "https://meatfish.id/gabung-kemitraan/",
        label: "program kemitraan frozen food Meat & Fish"
      },
      bridge: " dan ",
      secondLink: {
        href: "https://meatfish.co.id/franchise-makanan-beku/",
        label: "panduan franchise makanan beku"
      },
      conclusion: ". Keduanya dapat menjadi referensi tambahan untuk menilai produk, pasokan, dan dukungan operasional sebuah kemitraan."
    },
    franchise: {
      heading: "Referensi kemitraan usaha pangan",
      introduction: "Jika pembahasan di atas menjadi bahan pertimbangan membuka usaha, bandingkan pula ",
      firstLink: {
        href: "https://meatfish.id/gabung-kemitraan/",
        label: "program kemitraan frozen food Meat & Fish"
      },
      bridge: " dengan ",
      secondLink: {
        href: "https://meatfish.co.id/franchise-makanan-beku/",
        label: "panduan franchise makanan beku"
      },
      conclusion: " agar aspek produk, stok, dan dukungan operasional dapat dinilai lebih menyeluruh."
    },
    business: {
      heading: "Referensi pasokan untuk usaha kuliner",
      introduction: "Rencana usaha akan lebih kuat jika pasokan, mutu, dan ketersediaan stok dihitung sejak awal. Pelajari ",
      firstLink: {
        href: "https://meatfish.id/frozen-food-jenis-cara-pilih-dan-supplier-untuk-bisnis/",
        label: "panduan memilih supplier frozen food untuk bisnis"
      },
      bridge: " serta ",
      secondLink: {
        href: "https://meatfish.co.id/supplier-frozen-food-tangan-pertama-cara-cerdas-dapat-harga-terbaik/",
        label: "cara mendapatkan pasokan frozen food tangan pertama"
      },
      conclusion: " sebagai referensi sebelum menentukan pemasok."
    },
    seafood: {
      heading: "Referensi bahan baku ikan dan seafood",
      introduction: "Kualitas hidangan berbahan ikan sangat dipengaruhi oleh mutu bahan bakunya. Lihat ",
      firstLink: {
        href: "https://meatfish.id/produk-meatfish/",
        label: "pilihan ikan dan seafood beku Meat & Fish"
      },
      bridge: " dan ",
      secondLink: {
        href: "https://meatfish.co.id/frozen-fish-fillet-salmon-tilapia-tuna-dory/",
        label: "panduan memilih frozen fish fillet"
      },
      conclusion: " untuk menyesuaikan jenis ikan dengan menu yang akan diolah."
    },
    family: {
      heading: "Pilihan bahan pangan untuk keluarga",
      introduction: "Pembahasan pendidikan, kesehatan, dan tumbuh kembang dapat dilengkapi dengan perencanaan menu protein yang praktis. Jelajahi ",
      firstLink: {
        href: "https://meatfish.id/",
        label: "pilihan protein beku untuk keluarga"
      },
      bridge: " serta ",
      secondLink: {
        href: "https://meatfish.co.id/low-sodium-frozen-food-solusi-makanan-sehat-modern-mengapa-meatfish-hadir-sebagai-pilihan-terbaik/",
        label: "panduan frozen food rendah sodium"
      },
      conclusion: " sebagai referensi menyusun menu yang lebih terencana."
    },
    culinary: {
      heading: "Referensi bahan baku untuk menu kuliner",
      introduction: "Ide menu akan lebih mudah diterapkan ketika jenis dan sumber bahan bakunya sudah ditentukan. Temukan ",
      firstLink: {
        href: "https://meatfish.id/produk-meatfish/",
        label: "produk ikan, seafood, dan frozen food Meat & Fish"
      },
      bridge: " lalu pelajari ",
      secondLink: {
        href: "https://meatfish.co.id/supplier-ikan-frozen-untuk-restoran/",
        label: "cara memilih supplier ikan frozen"
      },
      conclusion: " untuk kebutuhan rumah tangga maupun usaha kuliner."
    }
  };

  function includesAny(text, terms) {
    return terms.some(function (term) { return text.indexOf(term) !== -1; });
  }

  function selectProfile(context) {
    var hostname = window.location.hostname.toLowerCase();
    var isEducationSite = hostname.indexOf("asysyams") !== -1;

    if (isEducationSite) {
      if (includesAny(context, ["franchise", "waralaba", "kemitraan", "bisnis", "usaha", "wirausaha" ])) {
        return referenceProfiles.educationBusiness;
      }
      return referenceProfiles.family;
    }

    if (includesAny(context, ["franchise", "waralaba", "kemitraan", "reseller"])) {
      return referenceProfiles.franchise;
    }
    if (includesAny(context, ["supplier", "distributor", "grosir", "usaha", "bisnis", "restoran", "katering", "hotel", "warung", "modal", "hpp", "food cost"])) {
      return referenceProfiles.business;
    }
    if (includesAny(context, ["ikan", "seafood", "udang", "cumi", "salmon", "tuna", "dori", "fillet", "hasil laut"])) {
      return referenceProfiles.seafood;
    }
    if (includesAny(context, ["anak", "keluarga", "gizi", "sehat", "kesehatan", "diet", "nutrisi", "sodium"])) {
      return referenceProfiles.family;
    }
    return referenceProfiles.culinary;
  }

  function addStyles() {
    if (document.getElementById("meatfish-contextual-links-style")) return;
    var style = document.createElement("style");
    style.id = "meatfish-contextual-links-style";
    style.textContent =
      ".meatfish-contextual-reference{display:block;clear:both;margin:36px 0 12px;padding:24px 26px;border-left:4px solid #d62828;border-radius:0 12px 12px 0;background:#f4f7fa;color:#26384a;box-sizing:border-box}" +
      ".meatfish-contextual-reference__label{margin:0 0 7px!important;color:#b42318!important;font-size:11px!important;font-weight:800!important;letter-spacing:.09em!important;line-height:1.4!important}" +
      ".meatfish-contextual-reference h2{margin:0 0 10px!important;color:#142536!important;font-size:22px!important;line-height:1.35!important}" +
      ".meatfish-contextual-reference p:last-child{margin:0!important;color:#34495e!important;font-size:16px!important;line-height:1.75!important}" +
      ".meatfish-contextual-reference a{color:#075ea8!important;font-weight:700!important;text-decoration:underline!important;text-underline-offset:3px}";
    document.head.appendChild(style);
  }

  function injectReference(target) {
    if (!target || target.querySelector(".meatfish-contextual-reference")) return;

    var article = target.closest("article") || document;
    var heading = article.querySelector("h1") || document.querySelector("h1");
    var context = ((heading ? heading.textContent : "") + " " + (target.textContent || "").slice(0, 6000)).toLowerCase();
    var profile = selectProfile(context);
    var reference = document.createElement("aside");
    reference.className = "meatfish-contextual-reference";
    reference.setAttribute("aria-label", "Referensi terkait");
    reference.setAttribute("data-meatfish-contextual-links", "2026-08");

    var label = document.createElement("p");
    label.className = "meatfish-contextual-reference__label";
    label.textContent = "REFERENSI TERKAIT";

    var title = document.createElement("h2");
    title.textContent = profile.heading;

    var paragraph = document.createElement("p");
    paragraph.appendChild(document.createTextNode(profile.introduction));

    var firstLink = document.createElement("a");
    firstLink.href = profile.firstLink.href;
    firstLink.textContent = profile.firstLink.label;
    paragraph.appendChild(firstLink);
    paragraph.appendChild(document.createTextNode(profile.bridge));

    var secondLink = document.createElement("a");
    secondLink.href = profile.secondLink.href;
    secondLink.textContent = profile.secondLink.label;
    paragraph.appendChild(secondLink);
    paragraph.appendChild(document.createTextNode(profile.conclusion));

    reference.appendChild(label);
    reference.appendChild(title);
    reference.appendChild(paragraph);
    target.appendChild(reference);
  }

  function run() {
    if (!document.body || !document.body.classList.contains("single-post")) return;
    addStyles();
    var targets = document.querySelectorAll("#mvp-content-main, .entry-body");
    Array.prototype.forEach.call(targets, function (target) {
      if (target.classList.contains("entry-body") && target.querySelector("#mvp-content-main")) return;
      injectReference(target);
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", run, { once: true });
  } else {
    run();
  }
})();
