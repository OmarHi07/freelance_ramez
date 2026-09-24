/* rawnaq_accessories1 — small progressive enhancements. Everything works without JavaScript. */
(function () {
  "use strict";

  function onReady(fn) {
    if (document.readyState !== "loading") fn();
    else document.addEventListener("DOMContentLoaded", fn);
  }

  /* ---------------------------------------------------------------- Toasts */
  function initToasts(root) {
    (root || document).querySelectorAll("[data-toast]").forEach(function (toast) {
      if (toast.dataset.bound) return;
      toast.dataset.bound = "1";
      var close = toast.querySelector("[data-toast-close]");
      var remove = function () { if (toast.parentNode) toast.parentNode.removeChild(toast); };
      if (close) close.addEventListener("click", remove);
      window.setTimeout(remove, 6000);
    });
  }

  /* ---------------------------------------------------------------- Product gallery */
  function initGallery() {
    var gallery = document.querySelector("[data-gallery]");
    if (!gallery) return;
    var main = gallery.querySelector("[data-gallery-main]");
    gallery.querySelectorAll("[data-gallery-thumb]").forEach(function (thumb) {
      thumb.addEventListener("click", function (event) {
        if (!main) return;
        event.preventDefault();
        main.src = thumb.dataset.full;
        main.alt = thumb.dataset.alt || "";
        gallery.querySelectorAll("[data-gallery-thumb]").forEach(function (other) {
          other.removeAttribute("aria-current");
        });
        thumb.setAttribute("aria-current", "true");
      });
    });
  }

  /* ---------------------------------------------------------------- Quantity + variants */
  function clampQuantity(input) {
    var min = parseInt(input.min || "1", 10);
    var max = parseInt(input.max || "10", 10);
    var value = parseInt(input.value || "1", 10);
    if (isNaN(value)) value = min;
    input.value = Math.max(min, Math.min(max, value));
  }

  function initBuyBox() {
    var form = document.querySelector("[data-buy-box]");
    if (!form) return;
    var qty = form.querySelector("[data-qty] input");
    form.querySelectorAll("[data-qty-step]").forEach(function (button) {
      button.addEventListener("click", function () {
        if (!qty) return;
        qty.value = (parseInt(qty.value || "1", 10) || 1) + parseInt(button.dataset.qtyStep, 10);
        clampQuantity(qty);
      });
    });
    if (qty) qty.addEventListener("change", function () { clampQuantity(qty); });

    var priceBlock = document.querySelector("[data-price-block]");
    var stockState = form.querySelector("[data-stock-state]");
    var submit = form.querySelector("button[type=submit]");
    form.querySelectorAll('input[name="variant"][type="radio"]').forEach(function (radio) {
      radio.addEventListener("change", function () {
        form.querySelectorAll(".variant-chip").forEach(function (chip) { chip.classList.remove("is-checked"); });
        if (radio.closest(".variant-chip")) radio.closest(".variant-chip").classList.add("is-checked");
        if (priceBlock) {
          var final = priceBlock.querySelector("[data-price-final]");
          var original = priceBlock.querySelector("[data-price-original]");
          var originalValue = priceBlock.querySelector("[data-price-original-value]");
          var note = priceBlock.querySelector("[data-price-note]");
          var discounted = radio.dataset.discounted === "1";
          if (final) final.textContent = radio.dataset.final;
          if (originalValue) originalValue.textContent = radio.dataset.original;
          if (original) original.hidden = !discounted;
          if (note) note.hidden = !discounted;
          var price = priceBlock.querySelector(".price");
          if (price) price.classList.toggle("price--sale", discounted);
        }
        if (stockState) stockState.textContent = radio.dataset.stockLabel || "";
        var max = Math.max(1, Math.min(10, parseInt(radio.dataset.max || "1", 10)));
        if (qty) { qty.max = max; clampQuantity(qty); }
        if (submit) submit.disabled = radio.disabled;
      });
      if (radio.checked && radio.closest(".variant-chip")) radio.closest(".variant-chip").classList.add("is-checked");
    });
  }

  /* ---------------------------------------------------------------- Filters (open on desktop) */
  function initFilters() {
    var details = document.querySelector("details.filters");
    if (!details || !window.matchMedia) return;
    if (window.matchMedia("(min-width: 1040px)").matches) details.open = true;
  }

  /* ---------------------------------------------------------------- Radio card fallback (:has) */
  function initRadioCards() {
    document.querySelectorAll(".address-option input[type=radio]").forEach(function (radio) {
      var sync = function () {
        document.querySelectorAll('.address-option input[name="' + radio.name + '"]').forEach(function (other) {
          other.closest(".address-option").classList.toggle("is-checked", other.checked);
        });
      };
      radio.addEventListener("change", sync);
      sync();
    });
  }

  onReady(function () {
    initToasts();
    initGallery();
    initBuyBox();
    initFilters();
    initRadioCards();
  });

  document.addEventListener("htmx:afterSwap", function (event) {
    initToasts(event.target);
  });
  document.addEventListener("htmx:responseError", function () {
    var region = document.getElementById("toast-region");
    if (!region) return;
    var lang = document.documentElement.lang;
    var text = lang === "ar" ? "حدث خطأ. يُرجى المحاولة مرة أخرى." : "Something went wrong. Please try again.";
    var toast = document.createElement("div");
    toast.className = "toast toast--error";
    toast.setAttribute("data-toast", "");
    var p = document.createElement("p");
    p.textContent = text;
    toast.appendChild(p);
    region.innerHTML = "";
    region.appendChild(toast);
    initToasts(region);
  });
})();
