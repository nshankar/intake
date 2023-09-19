import fsspec
import pytest

import intake.readers

pd = pytest.importorskip("pandas")
bindata = b"apple,beet,carrot\n" + b"a,1,0.1\nb,2,0.2\nc,3,0.3\n" * 100


@pytest.fixture()
def dataframe_file():
    m = fsspec.filesystem("memory")
    m.pipe("/data", bindata)
    return "memory://data"


@pytest.fixture()
def df(dataframe_file):
    return pd.read_csv(dataframe_file)


def test_pipelines_in_catalogs(dataframe_file, df):
    data = intake.readers.datatypes.CSV(url=dataframe_file)
    reader = intake.readers.readers.PandasCSV(data)
    reader2 = reader[["apple", "beet"]].set_index(keys="beet")
    cat = intake.readers.entry.Catalog()
    cat["mydata"] = reader2

    assert cat.mydata.read().equals(df[["apple", "beet"]].set_index(keys="beet"))
    assert cat.mydata.discover().equals(df[["apple", "beet"]].set_index("beet")[:10])

    cat["eq"] = reader.equals(other=reader)
    assert reader.equals(other=reader).read() is True
    assert cat.eq.read() is True


def test_parameters(dataframe_file, monkeypatch):
    data = intake.readers.datatypes.CSV(url=dataframe_file)
    reader = intake.readers.readers.PandasCSV(data)
    reader2 = reader[["apple", "beet"]].set_index(keys="beet")
    ent = reader2.to_entry()
    ent.extract_parameter(name="index_key", value="beet")
    assert ent.user_parameters["index_key"].default == "beet"

    assert str(ent.to_dict()).count("{index_key}") == 2  # once in select, once in set_index
    assert intake.readers.utils.descend_to_path("steps.1.2.keys", ent.kwargs) == "{index_key}"

    assert ent.to_reader() == reader2

    cat = intake.readers.entry.Catalog()
    cat.add_entry(reader2)
    datadesc = list(cat.data.values())[0]
    datadesc.extract_parameter(name="protocol", value="memory:")
    assert datadesc.kwargs["url"] == dataframe_file.replace("memory:", "{protocol}")
    datadesc.user_parameters["protocol"].set_default("env(TEMP_TEST)")
    monkeypatch.setenv("TEMP_TEST", "memory:")
    out = datadesc.to_data()
    assert out == data


def test_namespace(dataframe_file):
    data = intake.readers.datatypes.CSV(url=dataframe_file)
    reader = intake.readers.readers.PandasCSV(data)
    assert "np" in reader._namespaces
    assert reader.apply(getattr, "beet").np.max().read() == 3


calls = 0


def fails(x):
    global calls
    if calls < 2:
        calls += 1
        raise RuntimeError
    return x


def test_retry(dataframe_file):
    from intake.readers.readers import Retry

    data = intake.readers.datatypes.CSV(url=dataframe_file)
    reader = intake.readers.readers.PandasCSV(data)
    pipe = Retry(intake.readers.datatypes.ReaderData(reader.apply(fails)), allowed_exceptions=(ValueError,))
    cat = intake.readers.entry.Catalog()
    cat["ret1"] = pipe

    pipe = Retry(intake.readers.datatypes.ReaderData(reader.apply(fails)), allowed_exceptions=(RuntimeError,))
    cat["ret2"] = pipe

    with pytest.raises(RuntimeError):
        cat["ret1"].read()
    assert calls == 1

    assert cat["ret2"].read() is not None
    assert calls > 1


def dir_non_empty(d):
    import os

    return os.path.exists(d) and os.path.isdir(d) and bool(os.listdir(d))


# def test_custom_cache(dataframe_file, tmpdir):
#     from intake.readers.readers import Condition
#     cat = intake.readers.entry.Catalog()
#
#     data = intake.readers.datatypes.CSV(url=dataframe_file)
#     part = intake.readers.readers.PandasCSV(data)
#     cat["csv"] = part
#     output = intake.readers.datatypes.ReaderData(part.PandasToParquet(str(tmpdir)))
#     final = intake.readers.readers.PandasParquet(data2)
#     data3 = intake.readers.datatypes.ReaderData(final)
#     reader2 = Condition(data3, other=part)
#
#     out = reader2.read()
