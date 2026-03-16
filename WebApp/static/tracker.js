(function () {

const LOG_ENDPOINT = "http://10.20.0.5:9000/selenium-log"; // log server

function sendLog(data){
    try{
        navigator.sendBeacon(
            LOG_ENDPOINT,
            new Blob([JSON.stringify(data)], {type : "application/json"})
        );
    }catch(e){
        fetch(LOG_ENDPOINT,{
            method:"POST",
            headers:{"Content-Type":"application/json"},
            body:JSON.stringify(data)
        });
    }
}


/* -----------------------------
   Full XPath generator
----------------------------- */

function getXPath(el){

    if(el.id){
        return '//*[@id="' + el.id + '"]';
    }

    const parts=[];

    while(el && el.nodeType === Node.ELEMENT_NODE){

        let index=1;
        let sibling=el.previousSibling;

        while(sibling){
            if(
                sibling.nodeType === Node.ELEMENT_NODE &&
                sibling.nodeName === el.nodeName
            ){
                index++;
            }
            sibling=sibling.previousSibling;
        }

        parts.unshift(
            el.nodeName.toLowerCase()+"["+index+"]"
        );

        el=el.parentNode;
    }

    return "/"+parts.join("/");
}



/* -----------------------------
   Selector interception
----------------------------- */

const originalQuerySelector = document.querySelector;

document.querySelector = function(selector){

    sendLog({
        type:"selector",
        method:"querySelector",
        selector:selector,
        time:Date.now()
    });

    return originalQuerySelector.apply(this,arguments);
};


const originalGetElementById = document.getElementById;

document.getElementById = function(id){

    sendLog({
        type:"selector",
        method:"getElementById",
        selector:id,
        time:Date.now()
    });

    return originalGetElementById.apply(this,arguments);
};



/* -----------------------------
   XPath interception
----------------------------- */

const originalEvaluate = document.evaluate;

document.evaluate = function(xpath, contextNode, nsResolver, resultType, result){

    sendLog({
        type:"xpath-query",
        xpath:xpath,
        time:Date.now()
    });

    return originalEvaluate.apply(this,arguments);
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
            interval:diff,
            xpath:getXPath(e.target),
            time:now
        });

    }

    lastEventTime = now;

},true);


})();
