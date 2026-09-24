/* Reusable owner-dashboard image cropper.
 *
 * One component drives every image field: brand logo, brand banner, category
 * image and product images. A field opts in with data attributes:
 *
 *   <input type="file" data-crop="product_image" data-crop-ratio="1/1"
 *          data-crop-shape="square|circle" data-crop-width="1600" data-crop-height="1600">
 *
 * Progressive enhancement: with JavaScript off the same input is an ordinary
 * multipart file field and the server centre-crops the upload instead. The
 * cropped result is submitted as a real File in the same input, so nothing is
 * ever sent as base64 through a hidden text field. Object URLs are revoked as
 * soon as they are replaced, so repeated crops do not grow browser memory.
 */
(function () {
  "use strict";

  if (typeof window.Cropper !== "function") return;

  var JPEG_FALLBACK = "image/jpeg";
  var idCounter = 0;

  function t(node, key, fallback) {
    var value = node && node.dataset ? node.dataset[key] : "";
    return value || fallback;
  }

  function parseRatio(text) {
    var parts = String(text || "1/1").split("/");
    var w = parseFloat(parts[0]);
    var h = parseFloat(parts[1]);
    if (!isFinite(w) || !isFinite(h) || w <= 0 || h <= 0) return 1;
    return w / h;
  }

  function prefersReducedMotion() {
    return window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  }

  /* --------------------------------------------------------------------- */
  /* Modal                                                                  */
  /* --------------------------------------------------------------------- */

  function Modal(strings) {
    var self = this;
    idCounter += 1;
    var titleId = "crop-title-" + idCounter;

    var root = document.createElement("div");
    root.className = "crop-dialog";
    root.setAttribute("role", "dialog");
    root.setAttribute("aria-modal", "true");
    root.setAttribute("aria-labelledby", titleId);
    root.hidden = true;
    if (prefersReducedMotion()) root.classList.add("crop-dialog--no-motion");

    var panel = document.createElement("div");
    panel.className = "crop-dialog__panel";

    var head = document.createElement("div");
    head.className = "crop-dialog__head";
    var title = document.createElement("h2");
    title.className = "crop-dialog__title";
    title.id = titleId;
    head.appendChild(title);

    var hint = document.createElement("p");
    hint.className = "crop-dialog__hint";

    var stage = document.createElement("div");
    stage.className = "crop-dialog__stage";
    var image = document.createElement("img");
    image.alt = "";
    stage.appendChild(image);

    var controls = document.createElement("div");
    controls.className = "crop-dialog__controls";

    function button(label, icon, className) {
      var el = document.createElement("button");
      el.type = "button";
      el.className = "button button--ghost button--small " + (className || "");
      el.setAttribute("aria-label", label);
      el.title = label;
      var span = document.createElement("span");
      span.setAttribute("aria-hidden", "true");
      span.textContent = icon;
      el.appendChild(span);
      var text = document.createElement("span");
      text.className = "crop-dialog__button-text";
      text.textContent = label;
      el.appendChild(text);
      return el;
    }

    var zoomOut = button(strings.zoomOut, "−", "crop-dialog__icon-button");
    var zoomIn = button(strings.zoomIn, "+", "crop-dialog__icon-button");
    var rotateLeft = button(strings.rotateLeft, "↺", "crop-dialog__icon-button");
    var rotateRight = button(strings.rotateRight, "↻", "crop-dialog__icon-button");
    var reset = button(strings.reset, "⟲", "crop-dialog__icon-button");

    var zoomWrap = document.createElement("div");
    zoomWrap.className = "crop-dialog__zoom";
    var zoomLabel = document.createElement("label");
    zoomLabel.className = "crop-dialog__zoom-label";
    zoomLabel.textContent = strings.zoom;
    zoomLabel.htmlFor = "crop-zoom-" + idCounter;
    var zoom = document.createElement("input");
    zoom.type = "range";
    zoom.min = "0";
    zoom.max = "100";
    zoom.value = "0";
    zoom.step = "1";
    zoom.id = zoomLabel.htmlFor;
    zoom.className = "crop-dialog__zoom-input";
    zoomWrap.appendChild(zoomLabel);
    zoomWrap.appendChild(zoom);

    controls.appendChild(zoomOut);
    controls.appendChild(zoomWrap);
    controls.appendChild(zoomIn);
    controls.appendChild(rotateLeft);
    controls.appendChild(rotateRight);
    controls.appendChild(reset);

    var actions = document.createElement("div");
    actions.className = "crop-dialog__actions";
    var cancel = document.createElement("button");
    cancel.type = "button";
    cancel.className = "button button--ghost";
    cancel.textContent = strings.cancel;
    var apply = document.createElement("button");
    apply.type = "button";
    apply.className = "button";
    apply.textContent = strings.apply;
    actions.appendChild(cancel);
    actions.appendChild(apply);

    panel.appendChild(head);
    panel.appendChild(hint);
    panel.appendChild(stage);
    panel.appendChild(controls);
    panel.appendChild(actions);
    root.appendChild(panel);
    document.body.appendChild(root);

    this.root = root;
    this.panel = panel;
    this.image = image;
    this.title = title;
    this.hint = hint;
    this.stage = stage;
    this.zoom = zoom;

    var cropper = null;
    var objectUrl = "";
    var lastFocus = null;
    var onDone = null;
    var minZoomRatio = 1;

    function releaseUrl() {
      if (objectUrl) {
        URL.revokeObjectURL(objectUrl);
        objectUrl = "";
      }
    }

    function destroy() {
      if (cropper) {
        cropper.destroy();
        cropper = null;
      }
      releaseUrl();
      image.removeAttribute("src");
    }

    function close(result) {
      root.hidden = true;
      document.body.classList.remove("has-crop-dialog");
      destroy();
      var callback = onDone;
      onDone = null;
      if (lastFocus && typeof lastFocus.focus === "function") lastFocus.focus();
      lastFocus = null;
      if (callback) callback(result);
    }

    function focusables() {
      return Array.prototype.filter.call(
        panel.querySelectorAll("button, input, [href], [tabindex]:not([tabindex='-1'])"),
        function (el) { return !el.disabled && el.offsetParent !== null; }
      );
    }

    root.addEventListener("keydown", function (event) {
      if (event.key === "Escape") {
        event.preventDefault();
        close(null);
        return;
      }
      if (event.key !== "Tab") return;
      var items = focusables();
      if (!items.length) return;
      var first = items[0];
      var last = items[items.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    });

    root.addEventListener("click", function (event) {
      if (event.target === root) close(null);
    });

    cancel.addEventListener("click", function () { close(null); });

    function relativeZoom(value) {
      if (!cropper) return;
      // The slider maps 0-100 onto 1x-3x of the ratio that fills the frame, so
      // dragging it can never shrink the image below the crop box.
      cropper.zoomTo(minZoomRatio * (1 + (parseFloat(value) / 100) * 2));
    }

    zoom.addEventListener("input", function () { relativeZoom(zoom.value); });
    zoomIn.addEventListener("click", function () {
      zoom.value = String(Math.min(100, parseFloat(zoom.value) + 10));
      relativeZoom(zoom.value);
    });
    zoomOut.addEventListener("click", function () {
      zoom.value = String(Math.max(0, parseFloat(zoom.value) - 10));
      relativeZoom(zoom.value);
    });
    rotateLeft.addEventListener("click", function () { if (cropper) cropper.rotate(-90); });
    rotateRight.addEventListener("click", function () { if (cropper) cropper.rotate(90); });
    reset.addEventListener("click", function () {
      if (!cropper) return;
      cropper.reset();
      zoom.value = "0";
    });

    apply.addEventListener("click", function () {
      if (!cropper) return;
      var canvas = cropper.getCroppedCanvas({
        width: self.target.width,
        height: self.target.height,
        imageSmoothingQuality: "high",
        fillColor: "#ffffff"
      });
      if (!canvas) {
        close(null);
        return;
      }
      canvas.toBlob(function (blob) {
        if (!blob) {
          close(null);
          return;
        }
        close(new File([blob], self.target.filename, { type: blob.type || JPEG_FALLBACK }));
      }, JPEG_FALLBACK, 0.92);
    });

    /* Open the modal for one source (a File or a same-origin URL). */
    this.open = function (options, done) {
      lastFocus = document.activeElement;
      onDone = done;
      self.target = options.target;
      title.textContent = options.title;
      hint.textContent = options.hint || "";
      hint.hidden = !options.hint;
      stage.classList.toggle("is-circle", options.shape === "circle");
      stage.style.setProperty("--crop-ratio", options.cssRatio);
      zoom.value = "0";

      destroy();
      if (options.file) {
        objectUrl = URL.createObjectURL(options.file);
        image.src = objectUrl;
      } else {
        // Same-origin media, so the canvas stays untainted and can be exported.
        image.crossOrigin = "anonymous";
        image.src = options.url;
      }

      root.hidden = false;
      document.body.classList.add("has-crop-dialog");

      cropper = new window.Cropper(image, {
        aspectRatio: options.ratio,
        viewMode: 1,
        dragMode: "move",
        autoCropArea: 1,
        background: false,
        movable: true,
        zoomable: true,
        rotatable: true,
        scalable: false,
        guides: false,
        center: true,
        highlight: false,
        toggleDragModeOnDblclick: false,
        responsive: true,
        checkCrossOrigin: true,
        ready: function () {
          minZoomRatio = cropper.getImageData().ratio || 1;
          apply.focus();
        }
      });
    };

    this.destroy = destroy;
  }

  var sharedModal = null;
  function modal(strings) {
    if (!sharedModal) sharedModal = new Modal(strings);
    return sharedModal;
  }

  /* --------------------------------------------------------------------- */
  /* File inputs                                                            */
  /* --------------------------------------------------------------------- */

  function readStrings(input) {
    return {
      title: t(input, "cropTitle", "Crop image"),
      hint: t(input, "cropHint", ""),
      zoom: t(input, "cropZoom", "Zoom"),
      zoomIn: t(input, "cropZoomIn", "Zoom in"),
      zoomOut: t(input, "cropZoomOut", "Zoom out"),
      rotateLeft: t(input, "cropRotateLeft", "Rotate left"),
      rotateRight: t(input, "cropRotateRight", "Rotate right"),
      reset: t(input, "cropReset", "Reset"),
      cancel: t(input, "cropCancel", "Cancel"),
      apply: t(input, "cropApply", "Use this crop"),
      adjust: t(input, "cropAdjust", "Adjust crop"),
      remove: t(input, "cropRemove", "Remove"),
      primary: t(input, "cropPrimary", "Main picture")
    };
  }

  function targetFor(input) {
    return {
      width: parseInt(input.dataset.cropWidth || "1200", 10),
      height: parseInt(input.dataset.cropHeight || "1200", 10),
      filename: "crop.jpg"
    };
  }

  /* Replaces the files held by a file input. DataTransfer is the only way to
     write a FileList, and it is supported everywhere this dashboard runs. */
  function setFiles(input, files) {
    if (typeof DataTransfer !== "function") return false;
    var transfer = new DataTransfer();
    files.forEach(function (file) { transfer.items.add(file); });
    input.files = transfer.files;
    return true;
  }

  function bindInput(input) {
    if (input.dataset.cropBound) return;
    input.dataset.cropBound = "1";

    var strings = readStrings(input);
    var ratio = parseRatio(input.dataset.cropRatio);
    var cssRatio = String(input.dataset.cropRatio || "1/1").replace("/", " / ");
    var shape = input.dataset.cropShape === "circle" ? "circle" : "square";
    var multiple = input.multiple;

    var previews = document.createElement("ul");
    previews.className = "crop-previews";
    previews.setAttribute("aria-live", "polite");
    if (input.parentNode) input.parentNode.insertBefore(previews, input.nextSibling);

    /* Original picks, kept so "Adjust crop" can re-open the untouched source. */
    var entries = [];

    function revokeEntry(entry) {
      if (entry.previewUrl) {
        URL.revokeObjectURL(entry.previewUrl);
        entry.previewUrl = "";
      }
    }

    function commit() {
      setFiles(input, entries.map(function (entry) { return entry.cropped || entry.source; }));
    }

    function render() {
      previews.textContent = "";
      entries.forEach(function (entry, index) {
        var item = document.createElement("li");
        item.className = "crop-preview crop-preview--" + shape;

        var figure = document.createElement("div");
        figure.className = "crop-preview__frame";
        figure.style.setProperty("--crop-ratio", cssRatio);
        var img = document.createElement("img");
        img.alt = "";
        revokeEntry(entry);
        entry.previewUrl = URL.createObjectURL(entry.cropped || entry.source);
        img.src = entry.previewUrl;
        figure.appendChild(img);
        item.appendChild(figure);

        var meta = document.createElement("div");
        meta.className = "crop-preview__meta";
        if (multiple && index === 0) {
          var badge = document.createElement("span");
          badge.className = "crop-preview__badge";
          badge.textContent = strings.primary;
          meta.appendChild(badge);
        }

        var adjust = document.createElement("button");
        adjust.type = "button";
        adjust.className = "button button--ghost button--small";
        adjust.textContent = strings.adjust;
        adjust.addEventListener("click", function () {
          openFor(entry, adjust);
        });
        meta.appendChild(adjust);

        var remove = document.createElement("button");
        remove.type = "button";
        remove.className = "button button--ghost button--small button--danger-text";
        remove.textContent = strings.remove;
        remove.addEventListener("click", function () {
          revokeEntry(entry);
          entries.splice(entries.indexOf(entry), 1);
          commit();
          render();
          input.focus();
        });
        meta.appendChild(remove);

        item.appendChild(meta);
        previews.appendChild(item);
      });
    }

    function openFor(entry, returnFocusTo) {
      modal(strings).open(
        {
          file: entry.source,
          title: strings.title,
          hint: strings.hint,
          ratio: ratio,
          cssRatio: cssRatio,
          shape: shape,
          target: targetFor(input)
        },
        function (file) {
          if (file) {
            entry.cropped = file;
            commit();
            render();
          }
          if (returnFocusTo && document.body.contains(returnFocusTo)) returnFocusTo.focus();
        }
      );
    }

    /* Crop each chosen file in turn, so a multi-file pick stays independent. */
    function cropQueue(queue, index) {
      if (index >= queue.length) {
        commit();
        render();
        return;
      }
      var entry = queue[index];
      modal(strings).open(
        {
          file: entry.source,
          title: strings.title,
          hint: strings.hint,
          ratio: ratio,
          cssRatio: cssRatio,
          shape: shape,
          target: targetFor(input)
        },
        function (file) {
          if (file) entry.cropped = file;
          cropQueue(queue, index + 1);
        }
      );
    }

    input.addEventListener("change", function () {
      var picked = Array.prototype.slice.call(input.files || []);
      if (!picked.length) return;
      entries.forEach(revokeEntry);
      entries = picked.map(function (file) { return { source: file, cropped: null, previewUrl: "" }; });
      cropQueue(entries, 0);
    });

    /* "Adjust crop" on an image that is already stored: the current file is
       same-origin, so it can be re-cropped and submitted as a replacement. */
    var adjusters = document.querySelectorAll('[data-crop-adjust-for="' + input.id + '"]');
    Array.prototype.forEach.call(adjusters, function (button) {
      button.hidden = false;
      button.addEventListener("click", function () {
        modal(strings).open(
          {
            url: button.dataset.cropAdjust,
            title: strings.title,
            hint: strings.hint,
            ratio: ratio,
            cssRatio: cssRatio,
            shape: shape,
            target: targetFor(input)
          },
          function (file) {
            if (!file) {
              button.focus();
              return;
            }
            entries.forEach(revokeEntry);
            entries = [{ source: file, cropped: file, previewUrl: "" }];
            commit();
            render();
            button.focus();
          }
        );
      });
    });
  }

  function bind(root) {
    (root || document).querySelectorAll("input[type=file][data-crop]").forEach(bindInput);
  }

  window.RawnaqCropper = { bind: bind };

  if (document.readyState !== "loading") bind();
  else document.addEventListener("DOMContentLoaded", function () { bind(); });
})();
