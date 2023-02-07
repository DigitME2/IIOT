function html1(arr)
{
  let html = "";
  for(var x = 0; x<arr.length; x++)
  {
		html += "<ol class='r' style='outline: 1px solid white;'>";
		html += "<li>" + 'Test:' + x;
		html += "<li>" + 'Data:' + x;
		html += "<li>" + 'Delay:' + x;
		html += "<li>" + 'Enabled:' + x;
		html += "<li>" + 'Name:' + x;
		html += "<li>" + 'Street:' + x;
		html += "<li>" + 'City:' + x;
		html += "<li>" + 'Defined:' + x;
		html += "</ol>" ;
  }
   return html;
}

function html2(arr)
{
  let html = "";
  for(var x = 0; x<arr.length; x++)
  {
		html += `<ol class='r' style='outline: 1px solid white;'><li>Test:${x}<li>Data:${x}<li>Delay:${x}<li>Enabled:${x}<li>Name:${x}<li>Street:${x}<li>City:${x}<li>Defined:${x}</ol>`;
  }
  return html;
}

arr = [...Array(100).keys()]