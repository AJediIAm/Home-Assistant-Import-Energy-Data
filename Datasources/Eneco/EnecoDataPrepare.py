import os, sys, datetime, glob, math, json
import pandas as pd
from collections import namedtuple

# DataFilter named tuple definition
#   column: The name of the column on which the filter should be applied
#   value: The value on which should be filtered (regular expressions can be used)
#   equal: Boolean value indicating whether the filter should be inclusive or exclusive (True/False) 
DataFilter = namedtuple('DataFilter', ['column', 'value', 'equal'])

# OutputFileDefinition named tuple definition
#   outputFileName: The name of the output file
#   valueColumnName: The name of the column holding the value
#   dataFilters: A list of datafilters (see above the definition of a datafilter)
#   recalculate: Boolean value indication whether the data should be recalculated because the source is not an increasing value
OutputFileDefinition = namedtuple('FileDefinition', ['outputFileName', 'valueColumnName', 'dataFilters', 'recalculate'])


#*******************************************************************************************************************************************************
# TEMPLATE SETUP
#*******************************************************************************************************************************************************

# Name of the energy provider
energyProviderName = 'Eneco'

# Inputfile(s): filename extension
inputFileNameExtension = '.xlsx'
# Inputfile(s): Name of the column containing the date of the reading
inputFileDateColumnName = 'Datum'
# Inputfile(s): Date format used in the datacolumn
inputFileDateColumnFormat = '%d-%m-%Y'
# Inputfile(s): Data seperator being used in the .csv input file
inputFileDataSeperator = ''
# Inputfile(s): Decimal token being used in the input file
inputFileDataDecimal = ','
# Inputfile(s): Number of header rows in the input file
inputFileNumHeaderRows = 1
# Inputfile(s): Number of footer rows in the input file
inputFileNumFooterRows = 0
# Inputfile(s): Json path of the records (only needed for json files)
# Example: inputFileJsonPath = ['energy', 'values']
inputFileJsonPath = []
# Inputfile(s): Name or index of the excel sheet (only needed for excel files containing more sheets; leave at 0 for the first sheet)
inputFileExcelSheetName = 0

# Provide any data preparation code (if needed)
# Example: dataPreparation = "df['Energy Produced (Wh)'] = df['Energy Produced (Wh)'].str.replace(',', '').replace('\"', '').astype(int)"
dataPreparation = ""

# List of one or more output file definitions
outputFiles = [OutputFileDefinition('elec_feed_in_tariff_1_high_resolution.csv', 'Meterstand hoogtarief (El 2)', [], False),
               OutputFileDefinition('elec_feed_in_tariff_2_high_resolution.csv', 'Meterstand laagtarief (El 1)', [], False),
               OutputFileDefinition('elec_feed_out_tariff_1_high_resolution.csv', 'Meterstand hoogtarief (El 4)', [], False),
               OutputFileDefinition('elec_feed_out_tariff_2_high_resolution.csv', 'Meterstand laagtarief (El 3)', [], False),
               OutputFileDefinition('gas_high_resolution.csv', 'Meterstand', [], False)
              ]

#*******************************************************************************************************************************************************



# Prepare the input data
def prepareData(dataFrame: pd.DataFrame) -> pd.DataFrame:
    print('Preparing data');

    # Select only correct dates
    df = dataFrame.loc[(dataFrame[inputFileDateColumnName] >= datetime.datetime.strptime('01-01-1970', '%d-%m-%Y')) & (dataFrame[inputFileDateColumnName] <= datetime.datetime.strptime('31-12-2099', '%d-%m-%Y'))]
    
    # Make sure that the data is correctly sorted
    df.sort_values(by = inputFileDateColumnName, ascending = True, inplace = True)

    # Transform the date into unix timestamp for Home-Assistant
    df[inputFileDateColumnName] = (df[inputFileDateColumnName].view('int64') / 1000000000).astype('int64')
    
    # Execute any datapreparation code if provided
    exec(dataPreparation)

    return df


# Filter the data based on the provided dataFilter(s)
def filterData(dataFrame: pd.DataFrame, filters: DataFilter) -> pd.DataFrame:
    df = dataFrame
    # Iterate all the provided filters
    for dataFilter in filters:
        # Determine the subset based on the provided filter (regular expression)
        series = df[dataFilter.column].astype(str).str.contains(dataFilter.value, regex = True)
        
        # Validate whether the data is included or excluded
        if not dataFilter.equal:
            series = ~series
            
        df = df[series]

    return df


# Recalculate the data so that the value increases
def recalculateData(dataFrame :pd.DataFrame, dataColumnName: str) -> pd.DataFrame:
    df = dataFrame
    
    # Make the value column increasing (skip first row)
    previousRowIndex = -1
    for index, _ in df.iterrows():
        # Check if the current row contains a valid value
        if math.isnan(df.at[index, dataColumnName]):
            df.at[index, dataColumnName] = 0.0

        if previousRowIndex > -1:
            # Add the value of the previous row to the current row
            df.at[index, dataColumnName] = round(df.at[index, dataColumnName] + df.at[previousRowIndex, dataColumnName], 3)
        previousRowIndex = index
        
    return df


# Generate the datafile which can be imported
def generateImportDataFile(dataFrame: pd.DataFrame, outputFile: str, dataColumnName: str, filters: list[DataFilter], recalculate: bool):
    # Check if the column exists
    if dataColumnName in dataFrame.columns:
        print('Creating file: ' + outputFile);
        dataFrameFiltered = filterData(dataFrame, filters)
        
        # Check if we have to recalculate the data
        if recalculate:
            dataFrameFiltered = recalculateData(dataFrameFiltered, dataColumnName)
            
        # Select only the needed data
        dataFrameFiltered = dataFrameFiltered.filter([inputFileDateColumnName, dataColumnName])

        # Create the output file
        dataFrameFiltered.to_csv(outputFile, sep = ',', decimal = '.', header = False, index = False)
    else:
        print('Could not create file: ' + outputFile + ' because column: ' + dataColumnName + ' does not exist')


# Read the inputfile 
def readInputFile(inputFileName: str) -> pd.DataFrame:
    # Read the specified file
    print('Loading data: ' + inputFileName)

    # Check if we have a supported extension
    if inputFileNameExtension == '.csv':
        # Read the CSV file
        df = pd.read_csv(inputFileName, sep = inputFileDataSeperator, decimal = inputFileDataDecimal, skiprows = inputFileNumHeaderRows, skipfooter = inputFileNumFooterRows, engine = 'python')
    elif ((inputFileNameExtension == '.xlsx') or (inputFileNameExtension == '.xls')):
        # Read the XLSX/XLS file
        df = pd.read_excel(inputFileName, sheet_name = inputFileExcelSheetName, decimal = inputFileDataDecimal, skiprows = inputFileNumHeaderRows, skipfooter = inputFileNumFooterRows)
    elif inputFileNameExtension == '.json':
        # Read the JSON file
        jsonData = json.load(open(inputFileName))
        df = pd.json_normalize(jsonData, record_path = inputFileJsonPath)
    else:
        raise Exception('Unsupported extension: ' + inputFileNameExtension)

    df[inputFileDateColumnName] = pd.to_datetime(df[inputFileDateColumnName], format = inputFileDateColumnFormat, utc = True)
    # Remove the timezone (if it exists)
    df[inputFileDateColumnName] = df[inputFileDateColumnName].dt.tz_localize(None)
    
    return df


# Check if all the provided files have the correct extension
def correctFileExtensions(fileNames: list[str]) -> bool:
    # Check all filenames for the right extension
    for fileName in fileNames:
        _, fileNameExtension = os.path.splitext(fileName);
        if (fileNameExtension != inputFileNameExtension):
            return False
    return True


# Generate the datafiles which can be imported
def generateImportDataFiles(inputFileNames: str):
    # Find the file(s)
    fileNames = glob.glob(inputFileNames)
    if len(fileNames) > 0:
        print('Found files based on: ' + inputFileNames)
        
        # Check if all the found files are of the correct type
        if correctFileExtensions(fileNames):
            # Read all the found files and concat the data
            dataFrame = pd.concat(map(readInputFile, fileNames), ignore_index = True, sort = True)
        
            # Prepare the data
            dataFrame = prepareData(dataFrame)

            # Create the output files
            for outputFile in outputFiles:
                generateImportDataFile(dataFrame, outputFile.outputFileName, outputFile.valueColumnName, outputFile.dataFilters, outputFile.recalculate)

            print('Done')
        else:
            print('Only ' + inputFileNameExtension + ' datafiles are allowed');    
    else:
        print('No files found based on : ' + inputFileNames)


# Validate that the script is started from the command prompt
if __name__ == '__main__':
    print(energyProviderName + ' Data Prepare');
    print('');
    print('This python script prepares ' + energyProviderName + ' data for import into Home Assistant.')
    print('The files will be prepared in the current directory any previous files will be overwritten!')
    print('')
    if len(sys.argv) == 2:
        if input('Are you sure you want to continue [Y/N]?: ').lower().strip()[:1] == 'y':
            generateImportDataFiles(sys.argv[1])
    else:
        print(energyProviderName + 'PrepareData usage:')
        print(energyProviderName + 'PrepareData <' + energyProviderName + ' ' + inputFileNameExtension + ' filename (wildcard)>')