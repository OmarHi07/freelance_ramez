/* Owner dashboard helpers: mobile menu, colour pickers, image previews, formsets,
   promotion scope and the Standard/Custom option switch.
   Everything here is progressive enhancement: the server validates and saves the
   same result when JavaScript is unavailable. */
(function () {
  "use strict";

  function onReady(fn) {
    if (document.readyState !== "loading") fn();
    else document.addEventListener("DOMContentLoaded", fn);
  }

  function initNav() {
    var toggle = document.querySelector("[data-nav-toggle]");
    var nav = document.querySelector("[data-nav]");
    if (!toggle || !nav) return;
    toggle.addEventListener("click", function () {
      var open = nav.classList.toggle("is-open");
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
    });
  }

  function initColorInputs(root) {
    (root || document).querySelectorAll("input[data-color-input]").forEach(function (input) {
      if (input.dataset.bound) return;
      input.dataset.bound = "1";
      var picker = document.createElement("input");
      picker.type = "color";
      picker.setAttribute("aria-label", input.labels && input.labels[0] ? input.labels[0].textContent.trim() : "colour");
      var valid = /^#[0-9A-Fa-f]{6}$/;
      picker.value = valid.test(input.value) ? input.value : "#ffffff";
      var wrapper = document.createElement("div");
      wrapper.className = "color-pair";
      input.parentNode.insertBefore(wrapper, input);
      wrapper.appendChild(picker);
      wrapper.appendChild(input);
      picker.addEventListener("input", function () { input.value = picker.value.toUpperCase(); });
      input.addEventListener("input", function () { if (valid.test(input.value)) picker.value = input.value; });
    });
  }

  /* Plain previews for file inputs the cropper does not handle. Object URLs are
     revoked once the browser has decoded them, so repeated picks do not leak. */
  function initImagePreviews(root) {
    (root || document).querySelectorAll("input[type=file]:not([data-crop])").forEach(function (input) {
      if (input.dataset.previewBound) return;
      input.dataset.previewBound = "1";
      input.addEventListener("change", function () {
        var list = document.querySelector('[data-preview-list="' + input.id + '"]');
        var single = document.querySelector('[data-preview-for="' + input.id + '"]');
        if (list) {
          list.innerHTML = "";
          Array.prototype.forEach.call(input.files || [], function (file) {
            if (!/^image\//.test(file.type)) return;
            var item = document.createElement("li");
            var img = document.createElement("img");
            img.alt = "";
            img.src = URL.createObjectURL(file);
            img.addEventListener("load", function () { URL.revokeObjectURL(img.src); });
            var name = document.createElement("span");
            name.textContent = file.name;
            item.appendChild(img);
            item.appendChild(name);
            list.appendChild(item);
          });
        }
        if (single && input.files && input.files[0]) {
          var url = URL.createObjectURL(input.files[0]);
          single.addEventListener("load", function () { URL.revokeObjectURL(url); }, { once: true });
          single.src = url;
          single.hidden = false;
        }
      });
    });
  }

  function initFormsets() {
    document.querySelectorAll("[data-formset-add]").forEach(function (button) {
      var prefix = button.dataset.formsetAdd;
      var template = document.querySelector('[data-formset-template="' + prefix + '"]');
      var container = document.querySelector('[data-formset="' + prefix + '"]');
      var total = document.querySelector('input[name="' + prefix + '-TOTAL_FORMS"]');
      if (!template || !container || !total) return;
      button.hidden = false;
      button.addEventListener("click", function () {
        var index = parseInt(total.value, 10);
        var html = template.innerHTML.replace(/__prefix__/g, String(index));
        var wrapper = document.createElement("div");
        wrapper.innerHTML = html;
        var node = wrapper.firstElementChild;
        container.insertBefore(node, template);
        total.value = String(index + 1);
        initColorInputs(node);
        initOptionModes(node);
        initImagePreviews(node);
        if (window.RawnaqCropper) window.RawnaqCropper.bind(node);
        var first = node.querySelector("input:not([type=hidden])");
        if (first) first.focus();
      });
    });
  }

  /* Variant rows: "Standard" hides the option-name and colour fields, because the
     server fills both localized names itself. The inputs stay in the DOM (so an
     existing colour is preserved) but are cleared when switching to Standard, so
     what the owner sees is exactly what gets saved. */
  function initOptionModes(root) {
    (root || document).querySelectorAll("[data-variant-row]").forEach(function (row) {
      if (row.dataset.optionModeBound) return;
      row.dataset.optionModeBound = "1";
      var radios = row.querySelectorAll("input[type=radio][data-option-mode]");
      var custom = row.querySelector("[data-custom-fields]");
      var note = row.querySelector("[data-standard-note]");
      if (!radios.length || !custom) return;

      function selected() {
        for (var i = 0; i < radios.length; i += 1) if (radios[i].checked) return radios[i].value;
        return "custom";
      }

      function sync(clearOnStandard) {
        var standard = selected() === "standard";
        custom.hidden = standard;
        if (note) note.hidden = !standard;
        if (standard && clearOnStandard) {
          custom.querySelectorAll("input[type=text], input[type=color]").forEach(function (input) {
            input.value = "";
          });
        }
      }

      radios.forEach(function (radio) {
        radio.addEventListener("change", function () { sync(true); });
      });
      sync(false);
    });
  }

  function initPromotionScope() {
    var select = document.querySelector("select[data-promotion-scope]");
    if (!select) return;
    var sync = function () {
      document.querySelectorAll("[data-scope-target]").forEach(function (field) {
        var wrapper = field.closest(".scope-target");
        if (wrapper) wrapper.classList.toggle("is-hidden", field.dataset.scopeTarget !== select.value);
      });
    };
    select.addEventListener("change", sync);
    sync();
  }

  function initSlugs() {
    document.querySelectorAll("input[data-slug-from]").forEach(function (slug) {
      var source = document.getElementById(slug.dataset.slugFrom);
      if (!source) return;
      var touched = slug.value !== "";
      slug.addEventListener("input", function () { touched = true; });
      source.addEventListener("input", function () {
        if (touched) return;
        slug.value = source.value.toLowerCase().trim()
          .replace(/[^a-z0-9\s-]/g, "").replace(/[\s_-]+/g, "-").replace(/^-+|-+$/g, "");
      });
    });
  }

  onReady(function () {
    initNav();
    initColorInputs();
    initImagePreviews();
    initOptionModes();
    initFormsets();
    initPromotionScope();
    initSlugs();
  });
})();
