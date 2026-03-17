(function () {

const LOG_ENDPOINT = "http://10.20.0.5:9000/selenium-log"; // log server

function sendLog(data){
    try{
        // sendBeacon için type text/plain, preflight gitmesin
        navigator.sendBeacon(
            LOG_ENDPOINT,
            new Blob([JSON.stringify(data)], {type: "text/plain"})
        );
    }catch(e){
        // fallback fetch
        fetch(LOG_ENDPOINT, {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify(data),
            mode: "cors"  // cross-origin
        });
    }
}


/* -----------------------------
   Full XPath generator
----------------------------- */
function getXPath(el){
    if(el.id) return '//*[@id="' + el.id + '"]';
    const parts=[];
    while(el && el.nodeType === Node.ELEMENT_NODE){
        let index=1;
        let sibling=el.previousSibling;
        while(sibling){
            if(sibling.nodeType===Node.ELEMENT_NODE && sibling.nodeName===el.nodeName) index++;
            sibling=sibling.previousSibling;
        }
        parts.unshift(el.nodeName.toLowerCase()+"["+index+"]");
        el=el.parentNode;
    }
    return "/"+parts.join("/");
}

/* -----------------------------
   Selector interception
----------------------------- */
const originalQuerySelector = document.querySelector;
document.querySelector = function(selector){
    const el = originalQuerySelector.apply(this, arguments);
    sendLog({
        type: "selector",
        method: "querySelector",
        selector: selector,
        found: el !== null,
        time: Date.now()
    });
    return el;
};

const originalGetElementById = document.getElementById;
document.getElementById = function(id){
    const el = originalGetElementById.apply(this, arguments);
    sendLog({
        type: "selector",
        method: "getElementById",
        selector: id,
        found: el !== null,
        time: Date.now()
    });
    return el;
};

/* -----------------------------
   XPath interception
----------------------------- */
const originalEvaluate = document.evaluate;
document.evaluate = function(xpath, contextNode, nsResolver, resultType, result){
    let res;
    let found = false;
    try {
        res = originalEvaluate.apply(this, arguments);
        // XPathResult snapshot-type veya single-node için kontrol
        if(res instanceof XPathResult){
            if(res.snapshotLength !== undefined){
                found = res.snapshotLength > 0;
            } else if(res.singleNodeValue !== undefined){
                found = res.singleNodeValue !== null;
            }
        } else if(res instanceof Element){
            found = true;
        }
    } catch(e) {
        res = null;
        found = false;
    }

    sendLog({
        type:"xpath-query",
        xpath:xpath,
        found: found,
        time:Date.now()
    });

    return res;
};

/* -----------------------------
   Interaction logging
----------------------------- */
["click","input","focus","change","keydown"].forEach(eventType => {
    document.addEventListener(eventType,(e)=>{
        let value=null;
        let key=null;

        if(e.target && "value" in e.target){
            value=e.target.value;
        }

        if(eventType==="keydown"){
            key=e.key;
        }
        sendLog({
            type:"interaction",
            event:eventType,
            tag:e.target.tagName,
            id:e.target.id,
			name:e.target.name,
            class:e.target.className,
			key:key,
            value:value,
            xpath:getXPath(e.target),
            time:Date.now()
        });
    },true);
});

/* -----------------------------
   Final input value
----------------------------- */

document.addEventListener("change",(e)=>{

    if("value" in e.target){

        sendLog({
            type:"input-final",
            value:e.target.value,
            xpath:getXPath(e.target),
            time:Date.now()
        });

    }

},true);

/* -----------------------------
   Timing detection
----------------------------- */
let lastEventTime = Date.now();
document.addEventListener("click",(e)=>{
    const now = Date.now();
    const diff = now - lastEventTime;
    if(diff < 80){
        sendLog({
            type:"timing-alert",
            interval: diff,
            xpath: getXPath(e.target),
            time: now
        });
    }
    lastEventTime = now;
},true);

})();
