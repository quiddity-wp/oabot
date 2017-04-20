# -*- encoding: utf-8 -*-
from __future__ import unicode_literals

from settings import *
import subprocess32 as subprocess
import tempfile
import shutil
import os
import requests
import PyPDF2
from PyPDF2.utils import PyPdfError
from StringIO import StringIO

class RunnableError(Exception):
    pass


class AcademicPaperFilter(object):
   def classify_url(self, url):
        """
        Download a potential PDF file at a given URL and
        check if it looks like a legitimate scholarly paper.
        """
        try:
            r = requests.get(url, headers={'User-Agent':
                    OABOT_USER_AGENT}, verify=False)
            return self.check_nb_pages(r.content)
        except requests.exceptions.RequestException as e:
            print e
            return False

   def check_nb_pages(self, data):
        """
        Does this PDF contain enough pages?
        """
        try:
            s_io = StringIO(data)
            reader = PyPDF2.PdfFileReader(s_io)
            num_pages = reader.getNumPages()
            print("num pages: %d" % num_pages)
            return num_pages > 2
        except PyPdfError as e:
            return False

   #######################################################
   ##### The rest of this class is not currently used ####
   #######################################################

    # Most of this code is taken from the CiteSeerX extractor
    # Apache License 2.0
    # https://github.com/SeerLabs/new-csx-extractor

   def looks_legit(self, data):
        """
        Does this PDF look like a scholarly full text?
        """
        # make a temporary directory for filter jar to read/write to
        temp_dir = tempfile.mkdtemp()

        try:
            classifier_output = self.run_classifier(data, temp_dir)
        except RunnableError as e:
            print e
            classifier_output = False
        finally:
            #shutil.rmtree(temp_dir)
            pass

        return classifier_output

   def run_classifier(self, data, temp_dir):
        ### First, run PDFbox to extract plain text from the PDF

        # Write the pdf data to a temporary location so PDFBox can process it
        file_path = os.path.join(temp_dir, 'file.pdf')
        with open(file_path, 'wb') as f:
            f.write(data)

        try:
            command_args = ['java', '-jar', PDFBOX_JAR_PATH, 'ExtractText', '-console', '-encoding', 'UTF-8', file_path]
            status, stdout, stderr = external_process(command_args, timeout=30)
        except subprocess.TimeoutExpired:
            raise RunnableError('PDFBox timed out while processing document')

        if status != 0:
            raise RunnableError('PDFBox returned error status code {0}.\nPossible error:\n{1}'.format(status, stderr))

	# TODO temporary
	return True

        # We can use result from PDFBox directly, no manipulation needed
        pdf_plain_text = stdout
        with open(os.path.join(temp_dir, 'file.txt'), 'w') as pdf_text_file:
            pdf_text_file.write(pdf_plain_text)

        ## Then, run the classifier

        shutil.copy(FILTER_ACL_PATH, os.path.join(temp_dir, 'acl'))
        shutil.copy(FILTER_TRAIN_DATA_PATH, os.path.join(temp_dir,
'train_str_f43_paper.arff'))

        try:
            status, stdout, stderr = external_process(
                ['java', '-jar',
                FILTER_JAR_PATH, temp_dir+'/', 'file', 'paper'], timeout=20)
        except subprocess.TimeoutExpired as te:
            raise RunnableError('Filter Jar timed out while processing document')

        if status != 0:
            raise RunnableError('Filter Jar failed to execute sucessfully. Possible error:\n' + stderr)

        # last line of output should be 'true' or 'false' indicating if pdf is an academic paper or not

        # get rid of possible trailing blank lines
        lines = [line.strip() for line in stdout.split('\n') if line.strip()]
        result = lines[-1]
        if result.lower() == 'true':
            return True
        elif result.lower() == 'false':
            return False
        else:
            raise RunnableError('Last line of output from Jar should be either "true" or "false". Instead was: ' + result)



def external_process(process_args, input_data='', timeout=None):
   '''
   Pipes input_data via stdin to the process specified by process_args
and returns the results
   Arguments:
      process_args -- passed directly to subprocess.Popen(), see there
for more details
      input_data -- the data to pipe in via STDIN (optional)
      timeout -- number of seconds to time out the process after
(optional)
        IF the process timesout, a subprocess32.TimeoutExpired exception
will be raised
   Returns:
      (exit_status, stdout, stderr) -- a tuple of the exit status code
and strings containing stdout and stderr data
   Examples:
      >>> external_process(['grep', 'Data'], input_data="Some
String\nWith Data")
      (0, 'With Data\n', '')
   '''
   process = subprocess.Popen(process_args,
                              stdout=subprocess.PIPE,
                              stdin=subprocess.PIPE,
                              stderr=subprocess.PIPE)
   try:
      (stdout, stderr) =  process.communicate(input_data, timeout)
   except subprocess.TimeoutExpired as e:
      # cleanup process
      # see
      # https://docs.python.org/3.3/library/subprocess.html?highlight=subprocess#subprocess.Popen.communicate
      process.kill()
      process.communicate()
      raise e

   exit_status = process.returncode
   return (exit_status, stdout, stderr)


if __name__ == '__main__':
    import sys
    f = AcademicPaperFilter()
    #pdf_file = open(sys.argv[1], 'rb').read()
    #print f.looks_legit(pdf_file)
    print f.classify_url(sys.argv[1])
