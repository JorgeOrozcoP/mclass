
// global file reader
var reader = new FileReader();


//loader for body
function body_load(){

    // use this to eliminate cache in file input
    document.getElementById('input_slct').value = '';
    write_status('Waiting for file input.')

    // to disable button until user selects a file
    document.getElementById("submit_btn").disabled = true;

};


// write in the "status" p element
function write_status(str){ 

    document.getElementById('status').innerHTML = str
}


// on load handler. From:
// https://developer.mozilla.org/en-US/docs/Web/API/XMLHttpRequest/Using_XMLHttpRequest
function transferComplete() {

  message = "The transfer is complete.";
  console.log(message);
  console.log(this.statusText);
  console.log(this.responseText);
  
  // process the response

  result = JSON.parse(this.response);
  write_status(message); // result['message']; 
  document.getElementById('output_img').src = result['enc_img']; 

  document.getElementById("submit_btn").disabled = false;
}


function transferFailed(evt) {

  message = "An error has occurred.";
  console.log(message);
  console.log(this.statusText);
  console.log(this.responseText);
  write_status(message);

  document.getElementById("submit_btn").disabled = false;
}


function transferCanceled(evt) {
  message = "The transfer has been canceled by the user.";
  console.log(message);
  console.log(this.statusText);
  console.log(this.responseText);
  write_status(message);

  document.getElementById("submit_btn").disabled = false;
}


// validate if image is in correct format
function valid_img(){

    max_dims = [500, 500]
    preview = document.getElementById('preview_img');

    if(preview.naturalWidth >= max_dims[0] || preview.naturalHeight >= max_dims[1]){

        error_message = 'The image should be less than '.concat(max_dims[0].toString(), ' px and ', max_dims[1].toString(), ' px of width and heigth respectively.')

        write_status(error_message)

        return false

    }

    return true
}


// possible to use FormData, but could not parse in AWS
// https://developer.mozilla.org/en-US/docs/Web/API/FormData/Using_FormData_Objects
function http_call(){

    if(valid_img()){

        document.getElementById("submit_btn").disabled = true;
        write_status('Processing...')
        
        // --- http request ---
        var request = new XMLHttpRequest();

        // listeners
        request.addEventListener("load", transferComplete);
        request.addEventListener("error", transferFailed);
        request.addEventListener("abort", transferCanceled);

        var url = 'https://<restapiid>.execute-api.eu-central-1.amazonaws.com/Prod/myservice/';
        // var url = 'http://127.0.0.1:3000/detection';
        request.open("POST", url);
        
        request.send(reader.result);
    }

}


function img_preview(){

    img_file = document.getElementById('input_slct').files[0];
    preview = document.getElementById('preview_img');

    // read as base64
    // from https://developer.mozilla.org/en-US/docs/Web/API/FileReader/readAsDataURL
    reader.addEventListener("load", function () {
    preview.src = reader.result;
    }, false);

    if (img_file){
        reader.readAsDataURL(img_file);
        document.getElementById("submit_btn").disabled = false;
        write_status('Press the "Analyze" button.');
    }

}

