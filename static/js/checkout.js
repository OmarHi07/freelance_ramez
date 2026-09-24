/* Checkout: saved-address toggle and optional, consent-first geolocation.
   Location is requested only after the customer presses the button AND confirms
   the explanation. It is requested once (no tracking) and can be removed. */
(function () {
  "use strict";

  function onReady(fn) {
    if (document.readyState !== "loading") fn();
    else document.addEventListener("DOMContentLoaded", fn);
  }

  function initAddressToggle(form) {
    var radios = form.querySelectorAll('input[name="saved_address"]');
    var newAddress = form.querySelector("[data-new-address]");
    if (!radios.length || !newAddress) return;
    var sync = function () {
      var selected = form.querySelector('input[name="saved_address"]:checked');
      var useNew = !selected || selected.value === "";
      newAddress.hidden = !useNew;
    };
    radios.forEach(function (radio) { radio.addEventListener("change", sync); });
    sync();
  }

  function initGeolocation(form) {
    var section = form.querySelector("[data-geo]");
    if (!section) return;
    if (!("geolocation" in navigator) || !window.isSecureContext) {
      return; // keep hidden: manual address is the only path
    }
    section.hidden = false;

    var start = section.querySelector("[data-geo-start]");
    var consent = section.querySelector("[data-geo-consent]");
    var allow = section.querySelector("[data-geo-allow]");
    var cancel = section.querySelector("[data-geo-cancel]");
    var status = section.querySelector("[data-geo-status]");
    var remove = section.querySelector("[data-geo-remove]");
    var fields = {
      consent: form.querySelector('input[name="location_consent"]'),
      lat: form.querySelector('input[name="latitude"]'),
      lng: form.querySelector('input[name="longitude"]'),
      acc: form.querySelector('input[name="location_accuracy"]')
    };

    function clearFields() {
      fields.consent.value = "";
      fields.lat.value = "";
      fields.lng.value = "";
      fields.acc.value = "";
    }

    function setStatus(key, meters) {
      var text = status.dataset[key] || "";
      if (meters !== undefined) text = text.replace("%(meters)s", String(meters));
      status.textContent = text;
    }

    start.addEventListener("click", function () {
      consent.hidden = false;
      start.hidden = true;
      allow.focus();
    });

    cancel.addEventListener("click", function () {
      consent.hidden = true;
      start.hidden = false;
      start.focus();
    });

    allow.addEventListener("click", function () {
      consent.hidden = true;
      setStatus("msgLoading");
      navigator.geolocation.getCurrentPosition(
        function (position) {
          var coords = position.coords;
          fields.lat.value = coords.latitude.toFixed(6);
          fields.lng.value = coords.longitude.toFixed(6);
          fields.acc.value = Math.round(coords.accuracy || 0);
          fields.consent.value = "True";
          setStatus("msgSuccess", Math.round(coords.accuracy || 0));
          remove.hidden = false;
        },
        function (error) {
          clearFields();
          start.hidden = false;
          setStatus(error && error.code === 1 ? "msgDenied" : "msgUnavailable");
        },
        { enableHighAccuracy: true, timeout: 15000, maximumAge: 60000 }
      );
    });

    remove.addEventListener("click", function () {
      clearFields();
      remove.hidden = true;
      start.hidden = false;
      setStatus("msgRemoved");
      start.focus();
    });
  }

  onReady(function () {
    var form = document.querySelector("[data-checkout-form]");
    if (!form) return;
    initAddressToggle(form);
    initGeolocation(form);
  });
})();
