import test from "node:test";
import assert from "node:assert/strict";
import vm from "node:vm";
import {compileInteractiveTemplate,chooseTemplate} from "../src/interactive-template.mjs";

class El {
  constructor(tag="div"){this.tag=tag;this.children=[];this.value="";this.textContent="";this.style={};this.className="";}
  append(...nodes){this.children.push(...nodes);}
  replaceChildren(...nodes){this.children=nodes;}
  focus(){}
  click(){}
}
function runTemplate(kind){
  const {html,checks}=compileInteractiveTemplate({prompt:"シンプルなアプリを作って",mode:"web"},kind);
  assert.ok(checks.every(x=>x.passed));
  assert.ok(html.length<=19500);
  const script=html.match(/<script>([\s\S]*?)<\/script>/)?.[1];
  assert.ok(script,"trusted offline app script should exist");
  const map=new Map(),storage=new Map();
  const document={
    documentElement:{getAttribute:()=>kind},
    getElementById(id){if(!map.has(id))map.set(id,new El(id));return map.get(id);},
    createElement(tag){return new El(tag);}
  };
  const localStorage={
    getItem(key){return storage.get(key)||null;},
    setItem(key,v){storage.set(key,String(v));},
  };
  const ctx={document,localStorage,console,confirm:()=>true,Date,Math,JSON};
  vm.runInNewContext(script,ctx,{timeout:3000});
  return {html,map,storage,$:id=>document.getElementById(id)};
}
test("templates are not AI; only recognized types and user input always escaped",()=>{
  assert.equal(chooseTemplate("ToDoを作りたい"),"todo");
  assert.equal(chooseTemplate("メモを作りたい"),"notes");
  assert.equal(chooseTemplate("会社案内"),"landing");
  assert.throws(()=>chooseTemplate("hello","malicious"));
  const input='</script><script>alert("x")</script>';
  const {html}=compileInteractiveTemplate({prompt:input,mode:"web"},"todo");
  assert.doesNotMatch(html,/<script>alert\("x"\)<\/script>/);
  assert.match(html,/&lt;\/script&gt;/);
  assert.ok(!html.includes('src="https://'));
  assert.match(html,/AI生成ではなく/);
  assert.throws(()=>compileInteractiveTemplate({prompt:"X",mode:"app"},"todo"));
  assert.throws(()=>compileInteractiveTemplate({prompt:"X".repeat(1201),mode:"web"},"todo"));
});

test("real offline ToDo add / edit / complete / search / delete and persistence",()=>{
  const {$,storage}=runTemplate("todo");
  $("title").value="営業目標の確認";
  $("priority").value="high";
  $("due").value="2026-10-25";
  $("form").onsubmit({preventDefault(){}});
  let stored=JSON.parse([...storage.values()][0]);
  assert.equal(stored.length,1);
  assert.equal(stored[0].title,"営業目標の確認");
  assert.equal(stored[0].priority,"high");
  assert.equal(stored[0].due,"2026-10-25");
  let card=$("list").children[0];
  assert.equal(card.children[0].textContent,"営業目標の確認");
  card.children[2].children[0].onclick();
  stored=JSON.parse([...storage.values()][0]);
  assert.equal(stored[0].done,true);
  card=$("list").children[0];card.children[2].children[1].onclick();
  assert.equal($("title").value,"営業目標の確認");
  $("title").value="営業進捗を記録";
  $("form").onsubmit({preventDefault(){}});
  stored=JSON.parse([...storage.values()][0]);
  assert.equal(stored.length,1);
  assert.equal(stored[0].title,"営業進捗を記録");
  $("search").value="見つからない";
  $("search").oninput();
  assert.equal($("list").children[0].textContent,"該当するデータはありません。");
  $("search").value="営業";
  $("search").oninput();
  assert.equal($("list").children.length,1);
  $("list").children[0].children[2].children[2].onclick();
  assert.equal(JSON.parse([...storage.values()][0]).length,0);
});

test("real offline Notes add / edit / search / delete and persistence",()=>{
  const {$,storage}=runTemplate("notes");
  $("title").value="会議メモ";
  $("body").value="今日の決定事項";
  $("form").onsubmit({preventDefault(){}});
  let data=JSON.parse([...storage.values()][0]);assert.equal(data.length,1);
  assert.equal(data[0].body,"今日の決定事項");
  $("list").children[0].children[2].children[0].onclick();
  $("body").value="更新した決定事項";
  $("form").onsubmit({preventDefault(){}});
  data=JSON.parse([...storage.values()][0]);
  assert.equal(data[0].body,"更新した決定事項");
  $("search").value="更新";
  $("search").oninput();
  assert.equal($("list").children.length,1);
  $("list").children[0].children[2].children[1].onclick();
  assert.equal(JSON.parse([...storage.values()][0]).length,0);
});

test("opaque-origin preview with blocked storage still handles form and export",()=>{
  const source=compileInteractiveTemplate({prompt:"タスク",mode:"web"},"todo").html;
  const script=source.match(/<script>([\s\S]*?)<\/script>/)?.[1];
  const map=new Map();
  const document={
    documentElement:{getAttribute:()=>"todo"},
    getElementById(id){if(!map.has(id))map.set(id,new El(id));return map.get(id);},
    createElement(tag){return new El(tag);}
  };
  const localStorage={
    getItem(){throw Error("SecurityError");},
    setItem(){throw Error("SecurityError");}
  };
  vm.runInNewContext(script,{document,localStorage,confirm:()=>true,Date,Math,JSON},{timeout:3000});
  document.getElementById("title").value="Task in preview";
  assert.doesNotThrow(()=>document.getElementById("form").onsubmit({preventDefault(){}}));
  assert.equal(document.getElementById("list").children.length,1);
  assert.match(document.getElementById("status").textContent,/JSON/);
});
