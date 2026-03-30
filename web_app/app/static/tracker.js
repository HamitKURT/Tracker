(function () {
    "use strict";

    var _trackerErrorHandler = function (err, context) {
        try {
            if (window.ENV_DEBUG === 'true' && typeof console !== 'undefined') {
                console.warn('[Tracker Error]', context || 'Unknown', err && err.message ? err.message : String(err));
            }
        } catch (e) { }
    };

    try {

        var originalConsoleLog = console.log ? console.log.bind(console) : function () { };
        var originalConsoleError = console.error ? console.error.bind(console) : function () { };
        var originalConsoleWarn = console.warn ? console.warn.bind(console) : function () { };
        var originalFetch = window.fetch || null;
        var originalXHROpen = (XMLHttpRequest && XMLHttpRequest.prototype && XMLHttpRequest.prototype.open) || null;
        var originalXHRSend = (XMLHttpRequest && XMLHttpRequest.prototype && XMLHttpRequest.prototype.send) || null;
        var originalQuerySelector = document.querySelector || null;
        var originalGetElementById = document.getElementById || null;
        var originalEvaluate = document.evaluate || null;
        var originalGetElementsByClassName = document.getElementsByClassName || null;
        var originalGetElementsByTagName = document.getElementsByTagName || null;
        var originalGetElementsByName = document.getElementsByName || null;
        var originalGetBoundingClientRect = Element.prototype.getBoundingClientRect || null;
        var originalGetComputedStyle = window.getComputedStyle || null;
        var originalHTMLElementClick = HTMLElement.prototype.click || null;
        var originalElementQuerySelectorAll = Element.prototype.querySelectorAll || null;
        var originalElementQuerySelector = Element.prototype.querySelector || null;
        var originalElementMatches = Element.prototype.matches || null;
        var originalElementClosest = Element.prototype.closest || null;
        var originalGetAttribute = Element.prototype.getAttribute || null;
        var originalHasAttribute = Element.prototype.hasAttribute || null;
        var originalInnerText = Object.getOwnPropertyDescriptor(HTMLElement.prototype, 'innerText');
        var originalTextContent = Object.getOwnPropertyDescriptor(Node.prototype, 'textContent');
        var originalInputValue = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value');
        var originalTextAreaValue = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value');
        var originalInputChecked = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'checked');

        var DEFAULT_LOGSERVER_URL = 'http://mainlogserver.local:8084';

        var ENDPOINT_URL = navigator.webdriver
            ? (window.ENV_LOGSERVER_INTERNAL_URL || window.ENV_LOGSERVER_URL || DEFAULT_LOGSERVER_URL)
            : (window.ENV_LOGSERVER_URL || DEFAULT_LOGSERVER_URL);

        var CONFIG = {
            ENDPOINT_URL: ENDPOINT_URL,
            ENDPOINT_PATH: '/events',
            MAX_INTERACTION_RATE_MS: 80,
            DEBUG_MODE: window.ENV_DEBUG === 'true',
            MAX_RETRY_ATTEMPTS: 3,
            RESIZE_DEBOUNCE_MS: 500
        };

        var LOG_ENDPOINT = CONFIG.ENDPOINT_URL + CONFIG.ENDPOINT_PATH;

        (function detectAutomationGlobals() {
            try {
                var automationSignals = [];
                var globalKeys = [
                    '$cdc_', '$chrome_asyncScriptInfo', '__webdriver_callback', '__webdriver_func',
                    '__webdriver_script_func', '__webdriver_script_fn', '__webdriver_script_function',
                    '__selenium_evaluate', '__webdriver_evaluate', '__selenium_script',
                    '__webdriver_script', 'callSelenium', '_selenium', 'calledSelenium',
                    '_WEBDRIVER_ELEM_CACHE', 'driverHandleUnique', 'selenium', 'browser',
                    'getWebDriver', 'getAllWindowHandles', 'document.$w', 'document.$x'
                ];

                var hiddenKeys = Object.keys(window).filter(function (key) {
                    return globalKeys.some(function (signal) {
                        return key.indexOf(signal) === 0;
                    });
                });

                if (hiddenKeys.length > 0) {
                    automationSignals.push({
                        detected: true,
                        signals: hiddenKeys,
                        count: hiddenKeys.length
                    });
                }

                if (navigator.webdriver === true || navigator.webdriver === 'true') {
                    automationSignals.push({ detected: true, signal: 'navigator.webdriver', value: navigator.webdriver });
                }

                if (window.outerWidth === 0 && window.outerHeight === 0) {
                    automationSignals.push({ detected: true, signal: 'zero-outer-dimensions' });
                }

                if (window.screenX === 0 && window.screenY === 0 && window.outerWidth === 0 && window.outerHeight === 0) {
                    automationSignals.push({ detected: true, signal: 'headless-screen-position' });
                }

                var testCanvas = document.createElement('canvas');
                if (testCanvas) {
                    try {
                        var ctx = testCanvas.getContext('2d');
                        if (ctx && ctx.canvas && (ctx.canvas.width === 0 || ctx.canvas.height === 0)) {
                            automationSignals.push({ detected: true, signal: 'zero-canvas-size' });
                        }
                    } catch (e) { }
                }

                if (automationSignals.length > 0) {
                    sendEvent({
                        type: "automation-detected",
                        time: Date.now(),
                        signals: automationSignals,
                        severity: automationSignals.length >= 2 ? "high" : "medium"
                    });
                }
            } catch (e) { }
        })();

        var state = {
            sessionId: generateUUID(),
            lastInteractionTime: Date.now(),
            pageLoadTime: Date.now(),
            eventCount: 0,
            currentWindowWidth: window.innerWidth,
            currentWindowHeight: window.innerHeight,
            _sendDepth: 0
        };

        var cachedStaticPayload = {
            user_agent: navigator.userAgent,
            language: navigator.language,
            screen_resolution: window.screen.width + 'x' + window.screen.height,
            is_webdriver: navigator.webdriver || false
        };

        function generateUUID() {
            if (window.crypto && window.crypto.randomUUID) {
                return window.crypto.randomUUID();
            }
            return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
                var r = (Math.random() * 16) | 0,
                    v = c === 'x' ? r : (r & 0x3) | 0x8;
                return v.toString(16);
            });
        }

        function getXPath(el) {
            if (!el || el.nodeType !== Node.ELEMENT_NODE) return '';
            if (el.id) {
                var quote = el.id.indexOf("'") !== -1 ? '"' : "'";
                return '//*[@id=' + quote + el.id + quote + ']';
            }

            var parts = [];
            var current = el;

            while (current && current.nodeType === Node.ELEMENT_NODE) {
                var index = 1;
                var sibling = current.previousSibling;

                while (sibling) {
                    if (sibling.nodeType === Node.ELEMENT_NODE && sibling.nodeName === current.nodeName) {
                        index++;
                    }
                    sibling = sibling.previousSibling;
                }

                var nodeName = current.nodeName.toLowerCase();
                parts.unshift(nodeName + '[' + index + ']');
                current = current.parentNode;
            }
            return '/' + parts.join('/');
        }

        function throttle(fn, delay) {
            var lastCall = 0;
            return function () {
                var now = Date.now();
                if (now - lastCall >= delay) {
                    lastCall = now;
                    return fn.apply(this, arguments);
                }
            };
        }

        function debounce(fn, delay) {
            var timer;
            return function () {
                clearTimeout(timer);
                timer = setTimeout(function () { fn.apply(this, arguments); }.bind(this), delay);
            };
        }

        function buildBasePayload() {
            return {
                session_id: state.sessionId,
                url: window.location.href,
                user_agent: cachedStaticPayload.user_agent,
                is_webdriver: cachedStaticPayload.is_webdriver,
                language: cachedStaticPayload.language,
                screen_resolution: cachedStaticPayload.screen_resolution
            };
        }

        function deliverEvent(payload) {
            var payloadStr = JSON.stringify(payload);

            if (originalXHROpen && originalXHRSend) {
                try {
                    var xhr = new XMLHttpRequest();
                    originalXHROpen.call(xhr, "POST", LOG_ENDPOINT, true);
                    xhr.setRequestHeader("Content-Type", "text/plain");
                    originalXHRSend.call(xhr, payloadStr);
                    return;
                } catch (e) { }
            }

            if (originalFetch) {
                try {
                    originalFetch.call(window, LOG_ENDPOINT, {
                        method: "POST",
                        headers: { "Content-Type": "text/plain" },
                        body: payloadStr,
                        keepalive: true,
                        mode: "no-cors"
                    });
                    return;
                } catch (e) { }
            }

            if (navigator.sendBeacon) {
                var blob = new Blob([payloadStr], { type: "text/plain" });
                navigator.sendBeacon(LOG_ENDPOINT, blob);
            }
        }

        function sendEvent(data) {
            if (state._sendDepth > 0) return;
            if (!data || typeof data !== 'object') return;

            state._sendDepth++;

            try {
                var payload = buildBasePayload();
                for (var key in data) {
                    if (data.hasOwnProperty(key)) {
                        payload[key] = data[key];
                    }
                }
                payload.client_time = new Date().toISOString();
                state.eventCount++;

                deliverEvent(payload);
            } catch (e) { } finally {
                state._sendDepth--;
            }
        }

        if (originalQuerySelector) {
            document.querySelector = function (selector) {
                var result;
                try {
                    result = originalQuerySelector.apply(this, arguments);
                } catch (e) {
                    sendEvent({ type: "dom-query", method: "querySelector", selector: selector, found: false });
                    throw e;
                }
                sendEvent({
                    type: "dom-query",
                    method: "querySelector",
                    selector: selector,
                    found: result !== null
                });
                return result;
            };
        }

        if (originalGetElementById) {
            document.getElementById = function (id) {
                var result;
                try {
                    result = originalGetElementById.apply(this, arguments);
                } catch (e) {
                    sendEvent({ type: "dom-query", method: "getElementById", selector: id, found: false });
                    throw e;
                }
                sendEvent({
                    type: "dom-query",
                    method: "getElementById",
                    selector: id,
                    found: result !== null
                });
                return result;
            };
        }

        if (originalEvaluate) {
            document.evaluate = function (xpath, contextNode, nsResolver, resultType, result) {
                var res = null;
                var found = false;

                try {
                    res = originalEvaluate.apply(this, arguments);

                    if (res instanceof XPathResult) {
                        try {
                            if (res.resultType === XPathResult.ORDERED_NODE_SNAPSHOT_TYPE || res.resultType === XPathResult.UNORDERED_NODE_SNAPSHOT_TYPE) {
                                found = res.snapshotLength > 0;
                            } else if (res.singleNodeValue !== undefined) {
                                found = res.singleNodeValue !== null;
                            } else if (res.booleanValue !== undefined) {
                                found = res.booleanValue === true;
                            } else {
                                // Try to iterate through results
                                var iterResult = res;
                                if (iterResult.iterateNext) {
                                    found = iterResult.iterateNext() !== null;
                                }
                            }
                        } catch (innerErr) {
                            found = false;
                        }
                    } else if (res instanceof window.Element) {
                        found = true;
                    }
                } catch (e) {
                    sendEvent({ type: "xpath-query", xpath: xpath, found: false });
                    throw e;
                }

                sendEvent({
                    type: "xpath-query",
                    xpath: xpath,
                    found: found
                });

                return res;
            };
        }

        if (originalGetElementsByClassName) {
            document.getElementsByClassName = function (className) {
                var result;
                try {
                    result = originalGetElementsByClassName.apply(this, arguments);
                } catch (e) {
                    sendEvent({ type: "dom-query", method: "getElementsByClassName", selector: className, found: false });
                    throw e;
                }
                sendEvent({
                    type: "dom-query",
                    method: "getElementsByClassName",
                    selector: className,
                    found: result !== null && result.length > 0,
                    result_count: result ? result.length : 0
                });
                return result;
            };
        }

        if (originalGetElementsByTagName) {
            document.getElementsByTagName = function (tagName) {
                var result;
                try {
                    result = originalGetElementsByTagName.apply(this, arguments);
                } catch (e) {
                    sendEvent({ type: "dom-query", method: "getElementsByTagName", selector: tagName, found: false });
                    throw e;
                }
                sendEvent({
                    type: "dom-query",
                    method: "getElementsByTagName",
                    selector: tagName,
                    found: result !== null && result.length > 0,
                    result_count: result ? result.length : 0
                });
                return result;
            };
        }

        if (originalGetElementsByName) {
            document.getElementsByName = function (name) {
                var result;
                try {
                    result = originalGetElementsByName.apply(this, arguments);
                } catch (e) {
                    sendEvent({ type: "dom-query", method: "getElementsByName", selector: name, found: false });
                    throw e;
                }
                sendEvent({
                    type: "dom-query",
                    method: "getElementsByName",
                    selector: name,
                    found: result !== null && result.length > 0,
                    result_count: result ? result.length : 0
                });
                return result;
            };
        }

        (function setupElementInspectionInterception() {
            if (!Element.prototype.getBoundingClientRect) return;

            var safeSendEvent = function (data) {
                try {
                    sendEvent(data);
                } catch (e) { }
            };

            Element.prototype.getBoundingClientRect = function () {
                var result;
                try {
                    result = originalGetBoundingClientRect.apply(this, arguments);
                } catch (e) {
                    safeSendEvent({
                        type: "element-inspection",
                        method: "getBoundingClientRect",
                        success: false,
                        xpath: getXPath(this)
                    });
                    return null;
                }
                safeSendEvent({
                    type: "element-inspection",
                    method: "getBoundingClientRect",
                    success: true,
                    xpath: getXPath(this),
                    width: result ? result.width : 0,
                    height: result ? result.height : 0
                });
                return result;
            };

            if (originalGetComputedStyle) {
                window.getComputedStyle = function (element, pseudoElt) {
                    var result;
                    try {
                        result = originalGetComputedStyle.call(window, element, pseudoElt);
                    } catch (e) {
                        safeSendEvent({
                            type: "element-inspection",
                            method: "getComputedStyle",
                            success: false,
                            xpath: getXPath(element)
                        });
                        return null;
                    }
                    safeSendEvent({
                        type: "element-inspection",
                        method: "getComputedStyle",
                        success: true,
                        xpath: getXPath(element),
                        pseudo: pseudoElt || null
                    });
                    return result;
                };
            }

            var propDescriptors = [
                { name: 'offsetWidth', key: 'offsetWidth' },
                { name: 'offsetHeight', key: 'offsetHeight' },
                { name: 'offsetTop', key: 'offsetTop' },
                { name: 'offsetLeft', key: 'offsetLeft' },
                { name: 'clientWidth', key: 'clientWidth' },
                { name: 'clientHeight', key: 'clientHeight' },
                { name: 'clientTop', key: 'clientTop' },
                { name: 'clientLeft', key: 'clientLeft' },
                { name: 'scrollWidth', key: 'scrollWidth' },
                { name: 'scrollHeight', key: 'scrollHeight' },
                { name: 'scrollTop', key: 'scrollTop' },
                { name: 'scrollLeft', key: 'scrollLeft' }
            ];

            propDescriptors.forEach(function (prop) {
                var originalDescriptor = Object.getOwnPropertyDescriptor(HTMLElement.prototype, prop.name);
                if (!originalDescriptor) return;

                if (originalDescriptor.get) {
                    var originalGetter = originalDescriptor.get;
                    Object.defineProperty(HTMLElement.prototype, prop.name, {
                        get: function () {
                            var value;
                            try {
                                value = originalGetter.call(this);
                            } catch (e) {
                                safeSendEvent({
                                    type: "element-inspection",
                                    method: prop.name,
                                    success: false,
                                    xpath: getXPath(this)
                                });
                                return 0;
                            }
                            safeSendEvent({
                                type: "element-inspection",
                                method: prop.name,
                                success: true,
                                xpath: getXPath(this),
                                value: value
                            });
                            return value;
                        },
                        configurable: true,
                        enumerable: originalDescriptor.enumerable
                    });
                }
            });

            if (originalElementQuerySelectorAll) {
                Element.prototype.querySelectorAll = function (selector) {
                    var result;
                    try {
                        result = originalElementQuerySelectorAll.apply(this, arguments);
                    } catch (e) {
                        safeSendEvent({
                            type: "element-inspection",
                            method: "querySelectorAll",
                            success: false,
                            selector: selector,
                            xpath: getXPath(this)
                        });
                        throw e;
                    }
                    safeSendEvent({
                        type: "element-inspection",
                        method: "querySelectorAll",
                        success: true,
                        selector: selector,
                        xpath: getXPath(this),
                        result_count: result ? result.length : 0
                    });
                    return result;
                };
            }

            if (originalElementQuerySelector) {
                Element.prototype.querySelector = function (selector) {
                    var result;
                    try {
                        result = originalElementQuerySelector.apply(this, arguments);
                    } catch (e) {
                        safeSendEvent({
                            type: "element-inspection",
                            method: "querySelector",
                            success: false,
                            selector: selector,
                            xpath: getXPath(this)
                        });
                        throw e;
                    }
                    safeSendEvent({
                        type: "element-inspection",
                        method: "querySelector",
                        success: true,
                        selector: selector,
                        xpath: getXPath(this),
                        found: result !== null
                    });
                    return result;
                };
            }

            if (originalElementMatches) {
                Element.prototype.matches = function (selector) {
                    var result;
                    try {
                        result = originalElementMatches.call(this, selector);
                    } catch (e) {
                        safeSendEvent({
                            type: "element-inspection",
                            method: "matches",
                            success: false,
                            selector: selector,
                            xpath: getXPath(this)
                        });
                        throw e;
                    }
                    safeSendEvent({
                        type: "element-inspection",
                        method: "matches",
                        success: true,
                        selector: selector,
                        xpath: getXPath(this),
                        result: result
                    });
                    return result;
                };
            }

            if (originalElementClosest) {
                Element.prototype.closest = function (selector) {
                    var result;
                    try {
                        result = originalElementClosest.call(this, selector);
                    } catch (e) {
                        safeSendEvent({
                            type: "element-inspection",
                            method: "closest",
                            success: false,
                            selector: selector,
                            xpath: getXPath(this)
                        });
                        throw e;
                    }
                    safeSendEvent({
                        type: "element-inspection",
                        method: "closest",
                        success: true,
                        selector: selector,
                        xpath: getXPath(this),
                        found: result !== null
                    });
                    return result;
                };
            }

            HTMLElement.prototype.click = function () {
                safeSendEvent({
                    type: "element-action",
                    method: "click",
                    xpath: getXPath(this),
                    tag: this.tagName ? this.tagName.toLowerCase() : undefined
                });
                try {
                    return originalHTMLElementClick.apply(this, arguments);
                } catch (e) {
                    safeSendEvent({
                        type: "element-action",
                        method: "click",
                        xpath: getXPath(this),
                        success: false
                    });
                    throw e;
                }
            };

            if (originalGetAttribute) {
                Element.prototype.getAttribute = function (attrName) {
                    var result;
                    try {
                        result = originalGetAttribute.call(this, attrName);
                    } catch (e) {
                        safeSendEvent({
                            type: "data-extraction",
                            method: "getAttribute",
                            attribute: attrName,
                            success: false,
                            xpath: getXPath(this)
                        });
                        return null;
                    }
                    safeSendEvent({
                        type: "data-extraction",
                        method: "getAttribute",
                        attribute: attrName,
                        success: true,
                        xpath: getXPath(this),
                        value: result ? result.substring(0, 200) : null
                    });
                    return result;
                };
            }

            if (originalHasAttribute) {
                Element.prototype.hasAttribute = function (attrName) {
                    var result;
                    try {
                        result = originalHasAttribute.call(this, attrName);
                    } catch (e) {
                        safeSendEvent({
                            type: "data-extraction",
                            method: "hasAttribute",
                            attribute: attrName,
                            success: false,
                            xpath: getXPath(this)
                        });
                        return false;
                    }
                    safeSendEvent({
                        type: "data-extraction",
                        method: "hasAttribute",
                        attribute: attrName,
                        success: true,
                        xpath: getXPath(this),
                        result: result
                    });
                    return result;
                };
            }

            if (originalInnerText) {
                Object.defineProperty(HTMLElement.prototype, 'innerText', {
                    get: function () {
                        var result;
                        try {
                            result = originalInnerText.get.call(this);
                        } catch (e) {
                            safeSendEvent({
                                type: "data-extraction",
                                method: "innerText",
                                success: false,
                                xpath: getXPath(this)
                            });
                            throw e;
                        }
                        safeSendEvent({
                            type: "data-extraction",
                            method: "innerText",
                            success: true,
                            xpath: getXPath(this),
                            value: result ? result.substring(0, 500) : ''
                        });
                        return result;
                    },
                    set: function (val) {
                        var stack = '';
                        try { throw new Error(); } catch (err) { stack = err.stack || ''; }
                        var isSuspicious = stack.indexOf('<anonymous>') !== -1 || stack.indexOf('webdriver') !== -1;
                        safeSendEvent({
                            type: "value-manipulation",
                            method: "innerText",
                            xpath: getXPath(this),
                            value: val ? val.substring(0, 200) : '',
                            is_suspicious_stack: isSuspicious
                        });
                        return originalInnerText.set.call(this, val);
                    },
                    configurable: originalInnerText.configurable,
                    enumerable: originalInnerText.enumerable
                });
            }

            if (originalTextContent) {
                Object.defineProperty(Node.prototype, 'textContent', {
                    get: function () {
                        var result;
                        try {
                            result = originalTextContent.get.call(this);
                        } catch (e) {
                            safeSendEvent({
                                type: "data-extraction",
                                method: "textContent",
                                success: false,
                                xpath: getXPath(this)
                            });
                            throw e;
                        }
                        safeSendEvent({
                            type: "data-extraction",
                            method: "textContent",
                            success: true,
                            xpath: getXPath(this),
                            value: result ? result.substring(0, 500) : ''
                        });
                        return result;
                    },
                    set: function (val) {
                        var stack = '';
                        try { throw new Error(); } catch (err) { stack = err.stack || ''; }
                        var isSuspicious = stack.indexOf('<anonymous>') !== -1 || stack.indexOf('webdriver') !== -1;
                        safeSendEvent({
                            type: "value-manipulation",
                            method: "textContent",
                            xpath: getXPath(this),
                            value: val ? val.substring(0, 200) : '',
                            is_suspicious_stack: isSuspicious
                        });
                        return originalTextContent.set.call(this, val);
                    },
                    configurable: originalTextContent.configurable,
                    enumerable: originalTextContent.enumerable
                });
            }

            if (originalInputValue) {
                Object.defineProperty(HTMLInputElement.prototype, 'value', {
                    get: function () {
                        return originalInputValue.get.call(this);
                    },
                    set: function (val) {
                        var stack = '';
                        try { throw new Error(); } catch (err) { stack = err.stack || ''; }
                        var isSuspicious = stack.indexOf('<anonymous>') !== -1 || stack.indexOf('webdriver') !== -1;
                        safeSendEvent({
                            type: "value-manipulation",
                            method: "input-value",
                            xpath: getXPath(this),
                            tag: this.tagName ? this.tagName.toLowerCase() : 'input',
                            input_type: this.type || 'text',
                            value_length: val ? val.length : 0,
                            value_preview: val ? val.substring(0, 100) : '',
                            is_suspicious_stack: isSuspicious
                        });
                        return originalInputValue.set.call(this, val);
                    },
                    configurable: originalInputValue.configurable,
                    enumerable: originalInputValue.enumerable
                });
            }

            if (originalTextAreaValue) {
                Object.defineProperty(HTMLTextAreaElement.prototype, 'value', {
                    get: function () {
                        return originalTextAreaValue.get.call(this);
                    },
                    set: function (val) {
                        var stack = '';
                        try { throw new Error(); } catch (err) { stack = err.stack || ''; }
                        var isSuspicious = stack.indexOf('<anonymous>') !== -1 || stack.indexOf('webdriver') !== -1;
                        safeSendEvent({
                            type: "value-manipulation",
                            method: "textarea-value",
                            xpath: getXPath(this),
                            tag: 'textarea',
                            value_length: val ? val.length : 0,
                            value_preview: val ? val.substring(0, 100) : '',
                            is_suspicious_stack: isSuspicious
                        });
                        return originalTextAreaValue.set.call(this, val);
                    },
                    configurable: originalTextAreaValue.configurable,
                    enumerable: originalTextAreaValue.enumerable
                });
            }

            if (originalInputChecked) {
                Object.defineProperty(HTMLInputElement.prototype, 'checked', {
                    get: function () {
                        return originalInputChecked.get.call(this);
                    },
                    set: function (val) {
                        var stack = '';
                        try { throw new Error(); } catch (err) { stack = err.stack || ''; }
                        var isSuspicious = stack.indexOf('<anonymous>') !== -1 || stack.indexOf('webdriver') !== -1;
                        safeSendEvent({
                            type: "value-manipulation",
                            method: "checkbox-checked",
                            xpath: getXPath(this),
                            tag: 'input',
                            input_type: this.type || 'checkbox',
                            checked: val ? true : false,
                            is_suspicious_stack: isSuspicious
                        });
                        return originalInputChecked.set.call(this, val);
                    },
                    configurable: originalInputChecked.configurable,
                    enumerable: originalInputChecked.enumerable
                });
            }
        })();

        var INTERACTION_EVENTS = ["click", "input", "focus", "change", "keydown"];

        INTERACTION_EVENTS.forEach(function (eventType) {
            document.addEventListener(eventType, function (e) {
                try {
                    var target = e.target;

                    var eventData = {
                        type: "interaction",
                        event: eventType,
                        tag: target.tagName ? target.tagName.toLowerCase() : undefined,
                        id: target.id || undefined,
                        time: Date.now(),
                        name: target.name || undefined,
                        class: target.className && typeof target.className === 'string' ? target.className : undefined,
                        xpath: getXPath(target),
                        is_trusted: e.isTrusted !== undefined ? e.isTrusted : null
                    };

                    if (eventType === "click") {
                        eventData.page_x = e.pageX;
                        eventData.page_y = e.pageY;
                    }

                    if (eventType === "input" && target.type !== "password") {
                        eventData.value_length = target.value ? target.value.length : 0;
                    }

                    sendEvent(eventData);

                    if (e.isTrusted === false) {
                        sendEvent({
                            type: "automation-alert",
                            time: Date.now(),
                            event: eventType,
                            xpath: eventData.xpath,
                            alert: "synthetic-event-detected",
                            message: "Non-human (synthetic) event detected - likely automation"
                        });
                    }

                    if (eventType === "click") {
                        var now = Date.now();
                        var diff = now - state.lastInteractionTime;

                        if (diff < CONFIG.MAX_INTERACTION_RATE_MS) {
                            sendEvent({
                                type: "timing-alert",
                                event: "suspicious-click",
                                interval_ms: diff,
                                xpath: eventData.xpath,
                                suspicious: true
                            });
                        }
                        state.lastInteractionTime = now;
                    }
                } catch (e) { }
            }, true);
        });

        window.addEventListener("error", function (e) {
            var stack = '';
            try {
                if (e.error && e.error.stack) {
                    stack = e.error.stack.substring(0, 1000);
                }
            } catch (ex) { }

            sendEvent({
                type: "js-error",
                time: Date.now(),
                message: e.message,
                source: e.filename,
                lineno: e.lineno,
                colno: e.colno,
                stack: stack
            });
        });

        window.addEventListener("unhandledrejection", function (e) {
            var message = '';
            var stack = '';
            try {
                if (e.reason) {
                    message = typeof e.reason === 'string' ? e.reason : (e.reason.message || String(e.reason));
                    if (e.reason.stack) {
                        stack = e.reason.stack.substring(0, 1000);
                    }
                }
            } catch (ex) {
                message = 'Unknown rejection';
            }

            sendEvent({
                type: "promise-rejection",
                time: Date.now(),
                message: message.substring(0, 500),
                stack: stack
            });
        });

        console.error = function () {
            try {
                sendEvent({
                    type: "console-error",
                    level: "error",
                    time: Date.now(),
                    message: Array.prototype.slice.call(arguments).join(' ').substring(0, 500),
                    args_count: arguments.length
                });
            } catch (e) { }
            return originalConsoleError.apply(console, arguments);
        };

        console.warn = function () {
            try {
                sendEvent({
                    type: "console-error",
                    level: "warn",
                    time: Date.now(),
                    message: Array.prototype.slice.call(arguments).join(' ').substring(0, 500),
                    args_count: arguments.length
                });
            } catch (e) { }
            return originalConsoleWarn.apply(console, arguments);
        };

        document.addEventListener("visibilitychange", function () {
            sendEvent({
                type: "visibility",
                time: Date.now(),
                state: document.visibilityState
            });
        });

        if (originalFetch) {
            window.fetch = function (input, init) {
                var url = typeof input === 'string' ? input : (input && input.url ? input.url : String(input));
                var method = (init && init.method) ? init.method.toUpperCase() : 'GET';
                var startTime = Date.now();

                if (url.indexOf(LOG_ENDPOINT) !== -1) {
                    return originalFetch.apply(this, arguments);
                }

                return originalFetch.apply(this, arguments).then(function (response) {
                    sendEvent({
                        type: "network-request",
                        time: Date.now(),
                        request_url: url.substring(0, 200),
                        request_method: method,
                        status_code: response.status,
                        duration_ms: Date.now() - startTime,
                        request_type: "fetch",
                        success: response.ok
                    });
                    return response;
                }).catch(function (error) {
                    sendEvent({
                        type: "network-request",
                        time: Date.now(),
                        request_url: url.substring(0, 200),
                        request_method: method,
                        status_code: 0,
                        duration_ms: Date.now() - startTime,
                        request_type: "fetch",
                        success: false
                    });
                    throw error;
                });
            };
        }

        if (originalXHROpen && originalXHRSend) {
            XMLHttpRequest.prototype.open = function (method, url) {
                this._trackerMethod = method ? method.toUpperCase() : 'GET';
                this._trackerUrl = url ? String(url).substring(0, 200) : '';
                return originalXHROpen.apply(this, arguments);
            };

            XMLHttpRequest.prototype.send = function () {
                var self = this;

                if (self._trackerUrl && self._trackerUrl.indexOf(LOG_ENDPOINT) !== -1) {
                    return originalXHRSend.apply(this, arguments);
                }

                var startTime = Date.now();

                self.addEventListener("loadend", function () {
                    sendEvent({
                        type: "network-request",
                        time: Date.now(),
                        request_url: self._trackerUrl,
                        request_method: self._trackerMethod,
                        status_code: self.status,
                        duration_ms: Date.now() - startTime,
                        request_type: "xhr",
                        success: self.status >= 200 && self.status < 400
                    });
                });

                return originalXHRSend.apply(this, arguments);
            };
        }

        window.addEventListener("load", function () {
            setTimeout(function () {
                try {
                    var perfData = {
                        type: "performance",
                        time: Date.now()
                    };

                    var navEntries = performance.getEntriesByType
                        ? performance.getEntriesByType("navigation")
                        : [];

                    if (navEntries.length > 0) {
                        var nav = navEntries[0];
                        perfData.dom_content_loaded_ms = Math.round(nav.domContentLoadedEventEnd);
                        perfData.load_complete_ms = Math.round(nav.loadEventEnd);
                        perfData.dom_interactive_ms = Math.round(nav.domInteractive);
                        perfData.redirect_count = nav.redirectCount || 0;
                    } else if (performance.timing) {
                        var timing = performance.timing;
                        var navStart = timing.navigationStart || 0;
                        perfData.dom_content_loaded_ms = timing.domContentLoadedEventEnd ? timing.domContentLoadedEventEnd - navStart : 0;
                        perfData.load_complete_ms = timing.loadEventEnd ? timing.loadEventEnd - navStart : 0;
                        perfData.dom_interactive_ms = timing.domInteractive ? timing.domInteractive - navStart : 0;
                        perfData.redirect_count = (performance.navigation && performance.navigation.redirectCount) || 0;
                    }

                    if (performance.getEntriesByType) {
                        var resources = performance.getEntriesByType("resource");
                        perfData.resource_count = resources.length;
                        var totalSize = 0;
                        for (var i = 0; i < resources.length; i++) {
                            totalSize += resources[i].transferSize || 0;
                        }
                        perfData.transfer_size_bytes = totalSize;
                    }

                    if (performance.getEntriesByType) {
                        var paints = performance.getEntriesByType("paint");
                        for (var j = 0; j < paints.length; j++) {
                            if (paints[j].name === "first-paint") {
                                perfData.first_paint_ms = Math.round(paints[j].startTime);
                            }
                            if (paints[j].name === "first-contentful-paint") {
                                perfData.first_contentful_paint_ms = Math.round(paints[j].startTime);
                            }
                        }
                    }

                    sendEvent(perfData);
                } catch (e) { }
            }, 100);
        });

        document.addEventListener("submit", function (e) {
            try {
                var form = e.target;
                sendEvent({
                    type: "form-submit",
                    time: Date.now(),
                    form_id: form.id || undefined,
                    form_action: form.action || undefined,
                    form_method: (form.method || "GET").toUpperCase(),
                    field_count: form.elements ? form.elements.length : 0,
                    target_xpath: getXPath(form)
                });
            } catch (e) { }
        }, true);

        ["copy", "cut", "paste"].forEach(function (action) {
            document.addEventListener(action, function (e) {
                try {
                    var target = e.target;
                    var clipboardLength = 0;
                    if (e.clipboardData) {
                        clipboardLength = e.clipboardData.getData ? e.clipboardData.getData('text/plain').length : 0;
                    }
                    sendEvent({
                        type: "clipboard",
                        time: Date.now(),
                        action: action,
                        target_tag: target.tagName ? target.tagName.toLowerCase() : undefined,
                        target_id: target.id || undefined,
                        target_xpath: getXPath(target),
                        clipboard_length: clipboardLength
                    });
                } catch (e) { }
            }, true);
        });

        document.addEventListener("contextmenu", function (e) {
            try {
                var target = e.target;
                sendEvent({
                    type: "context-menu",
                    time: Date.now(),
                    x: e.pageX,
                    y: e.pageY,
                    target_tag: target.tagName ? target.tagName.toLowerCase() : undefined,
                    target_id: target.id || undefined,
                    target_xpath: getXPath(target)
                });
            } catch (e) { }
        }, true);

        var trackSelection = debounce(function () {
            try {
                var selection = window.getSelection();
                if (selection && selection.toString().length > 0) {
                    sendEvent({
                        type: "selection",
                        time: Date.now(),
                        selected_text: selection.toString().substring(0, 100),
                        anchor_xpath: selection.anchorNode ? getXPath(selection.anchorNode.parentElement || selection.anchorNode) : null,
                        focus_xpath: selection.focusNode ? getXPath(selection.focusNode.parentElement || selection.focusNode) : null
                    });
                }
            } catch (e) { }
        }, CONFIG.RESIZE_DEBOUNCE_MS);

        document.addEventListener("selectionchange", trackSelection);

        var trackResize = debounce(function () {
            var newWidth = window.innerWidth;
            var newHeight = window.innerHeight;

            sendEvent({
                type: "resize",
                time: Date.now(),
                width: newWidth,
                height: newHeight,
                previous_width: state.currentWindowWidth,
                previous_height: state.currentWindowHeight
            });

            state.currentWindowWidth = newWidth;
            state.currentWindowHeight = newHeight;
        }, CONFIG.RESIZE_DEBOUNCE_MS);

        window.addEventListener("resize", trackResize);

        function sendConnectionEvent(status) {
            var data = {
                type: "connection",
                time: Date.now(),
                status: status
            };

            if (navigator.connection) {
                data.effective_type = navigator.connection.effectiveType || undefined;
                data.downlink = navigator.connection.downlink || undefined;
            }

            sendEvent(data);
        }

        window.addEventListener("online", function () { sendConnectionEvent("online"); });
        window.addEventListener("offline", function () { sendConnectionEvent("offline"); });

        var originalMutationObserver = window.MutationObserver || window.WebKitMutationObserver;
        if (originalMutationObserver) {
            var throttledMutationSend = throttle(function (mutations, subtree) {
                try {
                    sendEvent({
                        type: "mutation-observer",
                        time: Date.now(),
                        mutation_count: mutations,
                        subtree: subtree
                    });
                } catch (e) { }
            }, CONFIG.RESIZE_DEBOUNCE_MS);

            var wrappedObserver = function (callback) {
                var wrappedCallback = function (mutations, observer) {
                    try {
                        var subtree = mutations && mutations.length > 0 ? mutations[0].target !== document.body : null;
                        throttledMutationSend(mutations ? mutations.length : 0, subtree);
                    } catch (e) { }
                    try {
                        callback.call(this, mutations, observer);
                    } catch (e) { }
                };
                try {
                    return new originalMutationObserver(wrappedCallback);
                } catch (e) {
                    return new originalMutationObserver(callback);
                }
            };
            wrappedObserver.prototype = originalMutationObserver.prototype;
            window.MutationObserver = wrappedObserver;
            if (window.WebKitMutationObserver) {
                window.WebKitMutationObserver = wrappedObserver;
            }
        }

        window.addEventListener("beforeunload", function () {
            var payload = buildBasePayload();
            payload.type = "page-unload";
            payload.client_time = new Date().toISOString();
            payload.time = Date.now();
            payload.time_on_page_ms = Date.now() - state.pageLoadTime;
            payload.event_count = state.eventCount;

            var payloadStr = JSON.stringify(payload);

            if (navigator.sendBeacon) {
                navigator.sendBeacon(
                    LOG_ENDPOINT,
                    new Blob([payloadStr], { type: "application/json" })
                );
            } else if (originalFetch) {
                originalFetch.call(window, LOG_ENDPOINT, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: payloadStr,
                    keepalive: true,
                    mode: "no-cors"
                });
            }
        });

        var navType = "navigate";
        try {
            if (performance.getEntriesByType) {
                var navEntries = performance.getEntriesByType("navigation");
                if (navEntries.length > 0) {
                    navType = navEntries[0].type || navType;
                }
            }
            if (navType === "navigate" && performance.navigation) {
                var types = ["navigate", "reload", "back_forward", "prerender"];
                var detected = types[performance.navigation.type];
                if (detected) {
                    navType = detected;
                }
            }
        } catch (e) { }

        sendEvent({
            type: "page-load",
            time: Date.now(),
            referrer: document.referrer || undefined,
            navigation_type: navType,
            from_url: document.referrer || undefined
        });

        sendEvent({
            type: "navigation",
            time: Date.now(),
            navigation_type: navType,
            referrer: document.referrer || undefined,
            from_url: document.referrer || undefined
        });

    } catch (err) {
        _trackerErrorHandler(err, 'tracker-initialization');
    }

})();
