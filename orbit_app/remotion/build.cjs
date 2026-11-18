const path = require('node:path');
const {bundle} = require('@remotion/bundler');
bundle({entryPoint:path.join(__dirname,'index.jsx'),outDir:path.join(__dirname,'dist')})
  .then(()=>console.log('ORBIT local composition built.'))
  .catch(error=>{console.error(error);process.exitCode=1;});
